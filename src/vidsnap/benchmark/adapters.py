"""Task adapters projecting formal benchmark cases onto the kernel contract."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast

from pydantic import Field, JsonValue

from vidsnap.benchmark.formal import FormalCase, parse_mcq_answer
from vidsnap.contracts import AcquisitionTool, Evidence, TerminalState, VideoGoal
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.models import StrictModel
from vidsnap.loop.events import RunEvent
from vidsnap.plugins.base import TranscriptionResponse
from vidsnap.runtime import KernelRunResult
from vidsnap.tasks.base import TaskVerification
from vidsnap.video.probe import ExtractedFrame, MediaProbe

_DIRECT_FRAME_SEQUENCE_FPS = 2

BenchmarkVariant = Literal["direct", "fixed", "agentic"]
DirectInputMode = Literal["video", "frames_2fps"]

_FAILED_GATES: tuple[str, ...] = (
    "schema_valid",
    "timestamps_in_bounds",
    "referenced_evidence_exists",
    "claims_are_supported",
    "required_sections_covered",
)


class MCQResult(StrictModel):
    """The strict final output of one formal MCQ case."""

    answer: str = Field(min_length=1, max_length=1)


class _ModelResponse(Protocol):
    """Structural provider counters shared by formal model calls."""

    text: str
    input_tokens: int
    output_tokens: int
    input_bytes: int
    usage_reported: bool


class _MCQModelPort(Protocol):
    """The only model operation the MCQ adapter may invoke."""

    async def answer_mcq(
        self,
        case: FormalCase,
        *,
        frames: tuple[ExtractedFrame, ...],
        transcript: str | None,
        video_path: Path | None,
        frame_sequence_fps: int | None = None,
    ) -> _ModelResponse:
        """Answer one MCQ from harness-controlled inputs."""


class _TranscriptionModelPort(Protocol):
    """The only model operation the transcription adapter may invoke."""

    async def transcribe_audio(self, audio_bytes: bytes) -> _ModelResponse:
        """Transcribe audio with the fixed registered model."""


class MCQTaskAdapter:
    """Project one registered MCQ case onto the kernel task-adapter contract."""

    output_model: type[MCQResult] = MCQResult

    def __init__(self, case: FormalCase) -> None:
        self._case = case
        self.goal = VideoGoal(objective=self._goal_text(case))

    async def request_final(
        self,
        model: _MCQModelPort,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> tuple[MCQResult, ProviderUsage]:
        """Run exactly one harness-controlled answer call and map real usage."""
        del probe
        response = await model.answer_mcq(
            self._case,
            frames=self._frames(evidence),
            transcript=self._transcript(evidence),
            video_path=None,
            frame_sequence_fps=self._frame_sequence_fps(evidence),
        )
        usage = ProviderUsage(
            model_calls=1,
            input_bytes=response.input_bytes,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            reported=response.usage_reported,
        )
        answer = parse_mcq_answer(response.text, self._case.option_labels)
        if answer is None:
            raise ValueError("provider returned no declared MCQ answer")
        return MCQResult(answer=answer), usage

    def parse_final(self, payload: dict[str, JsonValue]) -> MCQResult:
        """Accept only the strict declared-answer payload."""
        result = MCQResult.model_validate(payload)
        if result.answer not in self._case.option_labels:
            raise ValueError("answer must be one declared option label")
        return result

    def verify(
        self,
        output: MCQResult,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> TaskVerification:
        """Reproduce the five deterministic gates for one parsed answer."""
        schema_valid = output.answer in self._case.option_labels
        timestamps_in_bounds = all(
            0.0 <= item.start_seconds <= probe.duration_seconds
            and item.end_seconds <= probe.duration_seconds
            for item in evidence
        )
        evidence_exists = bool(evidence)
        gates = {
            "schema_valid": schema_valid,
            "timestamps_in_bounds": timestamps_in_bounds,
            "referenced_evidence_exists": evidence_exists,
            "claims_are_supported": schema_valid and evidence_exists,
            "required_sections_covered": True,
        }
        return TaskVerification(passed=all(gates.values()), gates=gates)

    def registered_subtitle(self) -> str | None:
        """Read the case's registered subtitle, if any, without invoking ASR."""
        subtitle_path = self._case.subtitle_path
        if subtitle_path is None:
            return None
        try:
            text = subtitle_path.read_text(encoding="utf-8")
        except OSError:
            return None
        return text.strip() or None

    @staticmethod
    def _frames(evidence: Sequence[Evidence]) -> tuple[ExtractedFrame, ...]:
        return tuple(
            ExtractedFrame(
                path=item.artifact_path,
                timestamp=item.start_seconds,
                perceptual_hash="",
            )
            for item in evidence
            if item.modality == "frame" and item.artifact_path is not None
        )

    @staticmethod
    def _transcript(evidence: Sequence[Evidence]) -> str | None:
        segments = [
            item.content
            for item in evidence
            if item.modality == "transcript" and item.content and item.content.strip()
        ]
        if not segments:
            return None
        return "\n".join(segments)

    @staticmethod
    def _frame_sequence_fps(evidence: Sequence[Evidence]) -> int | None:
        direct_frames = any(
            item.modality == "frame" and item.budget_class == "direct_baseline" for item in evidence
        )
        return _DIRECT_FRAME_SEQUENCE_FPS if direct_frames else None

    @staticmethod
    def _goal_text(case: FormalCase) -> str:
        return json.dumps(
            {"question": case.question, "options": case.options},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


class FormalTranscriptionAdapter:
    """Serve a pre-existing subtitle or exactly one measured transcribe call."""

    def __init__(
        self,
        model: _TranscriptionModelPort,
        *,
        subtitle_text: str | None = None,
    ) -> None:
        self._model = model
        self._subtitle_text = subtitle_text

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        """Return the subtitle when present, otherwise one measured model call."""
        del mime_type
        if self._subtitle_text is not None:
            return TranscriptionResponse(text=self._subtitle_text)
        response = await self._model.transcribe_audio(audio_bytes)
        usage = ProviderUsage(
            model_calls=1,
            input_bytes=response.input_bytes,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            reported=response.usage_reported,
        )
        return TranscriptionResponse(text=response.text, usage=usage)


class BenchmarkRunProjector:
    """Project one truthful kernel run onto the registered outcome schema."""

    def to_outcome(
        self,
        case: FormalCase,
        *,
        variant: BenchmarkVariant,
        result: KernelRunResult[MCQResult],
        direct_input_mode: DirectInputMode,
        latency_seconds: float,
    ) -> VariantOutcome:
        """Derive every outcome field from the kernel result and recorded events."""
        from vidsnap.benchmark.live import BenchmarkUsage, VariantOutcome

        events = self._read_events(result.run_path)
        selected_tools = tuple(
            cast(AcquisitionTool, str(event.payload.get("name")))
            for event in events
            if event.event_type == "tool.call.started"
        )
        usage = self._project_usage(events)
        if result.verification is not None:
            gates = dict(result.verification.gates)
            passed = result.verification.passed
        else:
            gates = {gate: False for gate in _FAILED_GATES}
            passed = False
        answer = result.output.answer if result.output is not None else None
        return VariantOutcome(
            case_id=case.case_id,
            variant=variant,
            terminal_state=result.terminal_state,
            answer=answer,
            correct=answer == case.answer,
            selected_tools=selected_tools,
            direct_input_mode=direct_input_mode if variant == "direct" else None,
            usage=BenchmarkUsage(
                model_calls=usage.model_calls,
                evidence_frames=usage.evidence_frames,
                input_bytes=usage.input_bytes,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                latency_seconds=latency_seconds,
            ),
            verifier_gates=gates,
            verifier_passed=passed,
            failure_reason=self._failure_reason(result.terminal_state),
        )

    @staticmethod
    def _read_events(run_path: Path) -> tuple[RunEvent, ...]:
        return tuple(
            RunEvent.model_validate_json(line)
            for line in (run_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    @staticmethod
    def _project_usage(events: Sequence[RunEvent]) -> _ProjectedUsage:
        """Sum only counters the run actually recorded on its terminal events."""
        model_calls = 0
        evidence_frames = 0
        input_bytes = 0
        input_tokens = 0
        output_tokens = 0
        for event in events:
            if event.event_type is not None and event.event_type.startswith("model.request."):
                if event.status in {"completed", "failed", "blocked"}:
                    model_calls += 1
            if event.event_type == "budget.updated":
                frames = event.payload.get("evidence_frames")
                if isinstance(frames, int) and not isinstance(frames, bool):
                    evidence_frames = frames
            if event.usage is None:
                continue
            if event.event_type is not None and event.event_type.startswith("tool.call."):
                model_calls += event.usage.model_calls
            input_bytes += event.usage.input_bytes
            input_tokens += event.usage.input_tokens
            output_tokens += event.usage.output_tokens
        return _ProjectedUsage(
            model_calls=model_calls,
            evidence_frames=evidence_frames,
            input_bytes=input_bytes,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    @staticmethod
    def _failure_reason(terminal_state: TerminalState) -> str | None:
        if terminal_state in (TerminalState.SUCCEEDED, TerminalState.PARTIAL):
            return None
        if terminal_state is TerminalState.BLOCKED:
            return "provider unavailable"
        return "benchmark case failed"


@dataclass(frozen=True, slots=True)
class _ProjectedUsage:
    model_calls: int
    evidence_frames: int
    input_bytes: int
    input_tokens: int
    output_tokens: int


if TYPE_CHECKING:
    from vidsnap.benchmark.live import VariantOutcome
