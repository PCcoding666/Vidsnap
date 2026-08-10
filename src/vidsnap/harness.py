"""The bounded, evidence-grounded Video Harness orchestration loop."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from vidsnap.config import TOKEN_PLAN_BASE_URL, HarnessConfig
from vidsnap.contracts import (
    Evidence,
    HarnessPolicy,
    TerminalState,
    VideoAnalysisResult,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.state_machine import BudgetExceeded, LoopController, LoopState
from vidsnap.loop.verifier import VerificationReport, verify_claims
from vidsnap.providers.asr import QwenAsrRecognizer, SpeechRecognizer
from vidsnap.providers.base import ModelResponse, ProviderError, ProviderUnavailable, VideoModelPort
from vidsnap.providers.qwen import QwenCompatibleClient
from vidsnap.skills import register_builtin_skills
from vidsnap.skills.base import SkillRegistry
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import ExtractedFrame, FFmpegMediaPort, MediaProbe
from vidsnap.video.sampling import AdaptiveSampler, FrameCandidate


@dataclass(slots=True)
class HarnessRunResult:
    """Truthful terminal output from one stateless harness invocation."""

    terminal_state: TerminalState
    run_path: Path
    result: VideoAnalysisResult | None = None
    failure_reason: str | None = None
    verification: VerificationReport | None = None

    @property
    def claims(self) -> list:
        """Expose result claims without pretending an absent result has evidence."""
        return self.result.claims if self.result is not None else []


@dataclass(slots=True)
class _RunContext:
    source: VideoSource
    goal: VideoGoal
    policy: HarnessPolicy
    controller: LoopController
    bundle: RunBundle
    media: FFmpegPort
    model: VideoModelPort
    recognizer: SpeechRecognizer | None
    sampler: AdaptiveSampler
    probe: MediaProbe | None = None
    evidence: list[Evidence] = field(default_factory=list)
    selected_frames: list[FrameCandidate] = field(default_factory=list)
    extracted_frames: list[ExtractedFrame] = field(default_factory=list)
    model_response: ModelResponse | None = None
    verification: VerificationReport | None = None
    targeted_windows: tuple[tuple[float, float], ...] = ()
    repair_pending: bool = False


class VideoHarness:
    """Execute a no-database, bounded evidence loop for one source and goal."""

    def __init__(
        self,
        config: HarnessConfig | None = None,
        *,
        media: FFmpegPort | None = None,
        model: VideoModelPort | None = None,
        recognizer: SpeechRecognizer | None = None,
        sampler: AdaptiveSampler | None = None,
    ) -> None:
        self.config = config or HarnessConfig.from_env()
        self.media = media or FFmpegMediaPort()
        self.model = model or QwenCompatibleClient(
            api_key=self.config.api_key,
            model_concurrency=self.config.model_concurrency,
            timeout_seconds=self.config.request_timeout_seconds,
        )
        self.recognizer = recognizer or QwenAsrRecognizer(api_key=self.config.api_key)
        self.sampler = sampler or AdaptiveSampler()
        self.loop_spec = default_loop_spec()
        self.skills = self._build_skill_registry()

    async def run(
        self,
        source: VideoSource,
        goal: VideoGoal,
        policy: HarnessPolicy | None = None,
    ) -> HarnessRunResult:
        """Run the approved loop to a truthful terminal state with one RunBundle."""
        effective_policy = policy or HarnessPolicy()
        run_path = effective_policy.output_dir or (Path.cwd() / "run" / str(uuid.uuid4()))
        bundle = RunBundle.create(
            run_path,
            loop_spec=self.loop_spec,
            provider_url=TOKEN_PLAN_BASE_URL,
        )
        context = _RunContext(
            source=source,
            goal=goal,
            policy=effective_policy,
            controller=LoopController(
                effective_policy,
                max_repair_rounds=self.loop_spec.max_repair_rounds,
            ),
            bundle=bundle,
            media=self.media,
            model=self.model,
            recognizer=self.recognizer,
            sampler=self.sampler,
        )
        failure_reason: str | None = None
        try:
            await self._execute(context)
        except BudgetExceeded:
            failure_reason = "budget exhausted"
        except ProviderUnavailable:
            context.controller.terminate(TerminalState.BLOCKED)
            failure_reason = "provider unavailable"
        except ProviderError:
            context.controller.terminate(TerminalState.FAILED)
            failure_reason = "provider error"
        except Exception:
            context.controller.terminate(TerminalState.FAILED)
            failure_reason = "unexpected harness error"

        if context.controller.terminal_state is None:
            context.controller.terminate(TerminalState.FAILED)
            failure_reason = failure_reason or "loop exited without a terminal state"
        bundle.append_event(
            "terminal",
            {
                "terminal_state": context.controller.terminal_state.value,
                "reason": failure_reason or "completed",
            },
        )
        bundle.finalize(context.controller.terminal_state)
        return HarnessRunResult(
            terminal_state=context.controller.terminal_state,
            run_path=run_path,
            result=context.model_response.result if context.model_response is not None else None,
            failure_reason=failure_reason,
            verification=context.verification,
        )

    async def _execute(self, context: _RunContext) -> None:
        while context.controller.state is not LoopState.TERMINAL:
            state = context.controller.state
            if state is LoopState.PROBE:
                context.controller.record_iteration()
                await self.skills.run("probe_media", context)
            elif state is LoopState.PLAN:
                context.bundle.append_event(
                    "plan",
                    {"skill_allow_list": list(self.loop_spec.allowed_skills)},
                )
                context.controller.transition(LoopState.GATHER)
            elif state is LoopState.GATHER:
                if context.repair_pending:
                    context.controller.record_iteration()
                    context.repair_pending = False
                await self.skills.run("transcribe_audio", context)
                await self.skills.run("sample_evidence", context)
                if context.controller.state is not LoopState.TERMINAL:
                    context.controller.transition(LoopState.UNDERSTAND)
            elif state is LoopState.UNDERSTAND:
                await self.skills.run("inspect_evidence", context)
                if context.controller.state is not LoopState.TERMINAL:
                    context.controller.transition(LoopState.SYNTHESIZE)
            elif state is LoopState.SYNTHESIZE:
                await self.skills.run("synthesize_result", context)
                if context.controller.state is not LoopState.TERMINAL:
                    context.controller.transition(LoopState.VERIFY)
            elif state is LoopState.VERIFY:
                await self.skills.run("verify_claims", context)
            else:
                raise RuntimeError(f"unhandled loop state: {state.value}")

    def _build_skill_registry(self) -> SkillRegistry:
        return register_builtin_skills(
            self.loop_spec,
            {
                "probe_media": self._probe_media,
                "transcribe_audio": self._transcribe_audio,
                "sample_evidence": self._sample_evidence,
                "inspect_evidence": self._inspect_evidence,
                "synthesize_result": self._synthesize_result,
                "verify_claims": self._verify_claims,
            },
        )

    async def _probe_media(self, context: _RunContext) -> None:
        context.probe = await context.media.probe(context.source.path)
        context.bundle.append_event(
            "probe_media",
            {
                "duration_seconds": context.probe.duration_seconds,
                "fps": context.probe.fps,
                "width": context.probe.width,
                "height": context.probe.height,
                "has_audio": context.probe.has_audio,
            },
        )
        context.controller.transition(LoopState.PLAN)

    async def _transcribe_audio(self, context: _RunContext) -> None:
        if context.probe is None or not context.probe.has_audio or context.recognizer is None:
            context.bundle.append_event("transcribe_audio", {"status": "skipped"})
            return
        extract_audio = getattr(context.media, "extract_audio", None)
        if extract_audio is None:
            context.bundle.append_event("transcribe_audio", {"status": "unsupported_media_port"})
            return
        audio_path = await extract_audio(
            context.source.path, context.bundle.path / "artifacts" / "audio.wav"
        )
        transcript = await context.recognizer.transcribe(audio_path.read_bytes())
        if transcript:
            evidence = Evidence(
                id=f"asr-{context.controller.iterations}",
                start_seconds=0,
                end_seconds=context.probe.duration_seconds,
                modality="transcript",
                content=transcript,
            )
            context.bundle.write_evidence(evidence)
            context.evidence.append(evidence)
            context.bundle.append_event("transcribe_audio", {"status": "captured"})
        else:
            context.bundle.append_event("transcribe_audio", {"status": "empty"})

    async def _sample_evidence(self, context: _RunContext) -> None:
        if context.probe is None:
            raise RuntimeError("probe_media must run before sample_evidence")
        candidates = await context.media.visual_candidates(context.source.path, context.probe)
        if context.targeted_windows:
            candidates = [
                candidate
                for candidate in candidates
                if any(
                    start <= candidate.timestamp <= end for start, end in context.targeted_windows
                )
            ]
        remaining_frame_budget = (
            context.policy.max_evidence_frames - context.controller.evidence_frames
        )
        if remaining_frame_budget < 1:
            context.controller.record_evidence_frames()
        selected = context.sampler.select(
            candidates,
            max_frames=min(
                remaining_frame_budget,
                self.loop_spec.budgets.max_evidence_frames,
            ),
        )
        if not selected:
            context.controller.terminate(
                TerminalState.PARTIAL if context.evidence else TerminalState.NO_OP
            )
            return
        context.controller.record_evidence_frames(len(selected))
        context.selected_frames = selected
        context.extracted_frames = await context.media.extract_frames(
            context.source.path,
            selected,
            context.bundle.path / "artifacts" / f"frames-{context.controller.iterations}",
        )
        context.bundle.append_event(
            "sample_evidence",
            {
                "selected_frames": len(context.extracted_frames),
                "targeted": bool(context.targeted_windows),
            },
        )
        context.targeted_windows = ()

    async def _inspect_evidence(self, context: _RunContext) -> None:
        if context.probe is None:
            raise RuntimeError("probe_media must run before inspect_evidence")
        if not context.extracted_frames:
            context.controller.terminate(
                TerminalState.PARTIAL if context.evidence else TerminalState.NO_OP
            )
            return
        for frame in context.extracted_frames:
            evidence = Evidence(
                id=f"frame-{len(context.evidence) + 1:03d}",
                start_seconds=frame.timestamp,
                end_seconds=frame.timestamp,
                modality="frame",
                artifact_path=frame.path,
            )
            context.bundle.write_evidence(evidence)
            context.evidence.append(evidence)
        context.bundle.append_event("inspect_evidence", {"captured": len(context.extracted_frames)})

    async def _synthesize_result(self, context: _RunContext) -> None:
        if not context.evidence:
            context.controller.terminate(TerminalState.NO_OP)
            return
        context.controller.record_model_call()
        context.model_response = await context.model.analyze_evidence(
            context.evidence, context.goal
        )
        context.bundle.write_result(context.model_response.result)
        context.bundle.append_event(
            "synthesize_result",
            {
                "input_tokens": context.model_response.input_tokens,
                "output_tokens": context.model_response.output_tokens,
            },
        )

    async def _verify_claims(self, context: _RunContext) -> None:
        if context.probe is None or context.model_response is None:
            raise RuntimeError("verification requires a probe and model response")
        result = context.model_response.result
        report = verify_claims(
            claims=result.claims,
            evidence=context.evidence,
            duration_seconds=context.probe.duration_seconds,
            result=result,
            required_sections=context.goal.required_sections,
        )
        context.verification = report
        context.bundle.append_event(
            "verify_claims",
            {"passed": report.passed, "failed_gates": list(report.failed_gates)},
        )
        if report.passed:
            context.controller.terminate(TerminalState.SUCCEEDED)
            return
        if (
            context.controller.repair_rounds < self.loop_spec.max_repair_rounds
            and context.controller.iterations < context.policy.max_iterations
        ):
            context.targeted_windows = report.targeted_resample_seconds
            context.controller.transition(LoopState.REPAIR)
            context.bundle.append_event(
                "repair",
                {"targeted_windows": [list(window) for window in context.targeted_windows]},
            )
            context.repair_pending = True
            context.controller.transition(LoopState.GATHER)
            return
        context.controller.terminate(TerminalState.PARTIAL)
