"""End-to-end bounded harness behavior with local fake ports."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Sequence
from pathlib import Path

import pytest

from vidsnap.contracts import (
    Claim,
    EvidenceReference,
    HarnessPolicy,
    ProviderUsage,
    ToolPlan,
    VideoAnalysisResult,
    VideoGoal,
    VideoSource,
)
from vidsnap.contracts.agent import AgentDecision, ToolCallRequest
from vidsnap.harness import VideoHarness
from vidsnap.providers.base import (
    AgentDecisionResponse,
    AgentStepRequest,
    ModelResponse,
    ProviderError,
    ProviderUnavailable,
    ToolPlanResponse,
)
from vidsnap.video.probe import ExtractedFrame, MediaProbe
from vidsnap.video.sampling import FrameCandidate


class FakeMediaPort:
    def __init__(self, *, has_audio: bool = False) -> None:
        self.has_audio = has_audio
        self.visual_candidate_calls = 0
        self.audio_calls: list[tuple[float, float | None]] = []

    async def probe(self, source: Path) -> MediaProbe:
        del source
        return MediaProbe(
            duration_seconds=10,
            fps=24,
            width=640,
            height=360,
            has_audio=self.has_audio,
        )

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        del source, probe
        self.visual_candidate_calls += 1
        return [
            FrameCandidate(timestamp=1, score=1, perceptual_hash="first"),
            FrameCandidate(timestamp=9, score=1, perceptual_hash="last"),
        ]

    async def extract_frames(
        self,
        source: Path,
        candidates: list[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        del source
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for index, candidate in enumerate(candidates):
            frame_path = output_dir / f"{index}.jpg"
            frame_path.write_bytes(b"test-image")
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=candidate.timestamp,
                    perceptual_hash=candidate.perceptual_hash,
                )
            )
        return frames

    async def extract_audio(
        self,
        source: Path,
        output_path: Path,
        *,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Path:
        del source
        self.audio_calls.append((start_seconds, end_seconds))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"test-audio")
        return output_path


class FakeRecognizer:
    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        assert audio_bytes == b"test-audio"
        assert mime_type == "audio/wav"
        return "The speaker says hello."


class FakePlanner:
    def __init__(self, plan: ToolPlan) -> None:
        self.plan = plan

    async def plan_tools(self, probe: MediaProbe, goal: VideoGoal) -> ToolPlanResponse:
        assert probe.has_audio
        assert goal.objective == "What was said?"
        return ToolPlanResponse(plan=self.plan, input_tokens=11, output_tokens=3)


class ScriptedAgentModel:
    """Replays scripted agent decisions in order; legacy plan_tools is a tripwire."""

    def __init__(self, decisions: Sequence[AgentDecision]) -> None:
        self.decisions: deque[AgentDecision] = deque(decisions)
        self.requests: list[AgentStepRequest] = []
        self.plan_tools_calls = 0

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        self.requests.append(request)
        if not self.decisions:
            raise AssertionError("ScriptedAgentModel received an unexpected decide_next call")
        return AgentDecisionResponse(
            decision=self.decisions.popleft(),
            usage=ProviderUsage(reported=False),
        )

    async def plan_tools(self, probe: MediaProbe, goal: VideoGoal) -> ToolPlanResponse:
        del probe, goal
        self.plan_tools_calls += 1
        raise AssertionError("agentic mode must not call the legacy one-shot plan_tools port")


class FakeModel:
    async def analyze_evidence(self, evidence, goal: VideoGoal) -> ModelResponse:
        del goal
        return ModelResponse(
            result=VideoAnalysisResult(
                summary="A fake grounded result.",
                claims=[
                    Claim(
                        text="A visible event occurs.",
                        evidence=[EvidenceReference(evidence_id=evidence[0].id)],
                    )
                ],
            ),
        )


@pytest.mark.asyncio
async def test_harness_returns_supported_claims_and_trace(tmp_path) -> None:
    result = await VideoHarness(media=FakeMediaPort(), model=FakeModel()).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize the demonstration"),
        HarnessPolicy(output_dir=tmp_path / "run"),
    )

    assert result.terminal_state.value == "SUCCEEDED"
    assert result.claims[0].evidence
    assert (tmp_path / "run" / "manifest.json").exists()
    assert (
        json.loads((tmp_path / "run" / "manifest.json").read_text())["terminal_state"]
        == "SUCCEEDED"
    )


@pytest.mark.asyncio
async def test_harness_marks_missing_local_provider_key_as_blocked(tmp_path) -> None:
    class BlockedModel:
        async def analyze_evidence(self, evidence, goal: VideoGoal) -> ModelResponse:
            del evidence, goal
            raise ProviderUnavailable("no local key")

    result = await VideoHarness(media=FakeMediaPort(), model=BlockedModel()).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize the demonstration"),
        HarnessPolicy(output_dir=tmp_path / "blocked-run"),
    )

    assert result.terminal_state.value == "BLOCKED"
    assert result.claims == []


@pytest.mark.asyncio
async def test_harness_never_marks_empty_or_unsupported_claim_output_as_success(tmp_path) -> None:
    class EmptyModel:
        async def analyze_evidence(self, evidence, goal: VideoGoal) -> ModelResponse:
            del evidence, goal
            return ModelResponse(
                result=VideoAnalysisResult(summary="No supported facts.", claims=[])
            )

    result = await VideoHarness(media=FakeMediaPort(), model=EmptyModel()).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize the demonstration"),
        HarnessPolicy(output_dir=tmp_path / "empty-run"),
    )

    assert result.terminal_state.value == "PARTIAL"
    assert result.verification is not None
    assert "claims_are_supported" in result.verification.failed_gates


@pytest.mark.asyncio
async def test_harness_returns_partial_when_claim_evidence_does_not_exist(tmp_path) -> None:
    class UnsupportedModel:
        async def analyze_evidence(self, evidence, goal: VideoGoal) -> ModelResponse:
            del evidence, goal
            return ModelResponse(
                result=VideoAnalysisResult(
                    summary="A result with a missing reference.",
                    claims=[
                        Claim(
                            text="Unsupported fact.",
                            evidence=[EvidenceReference(evidence_id="missing")],
                        )
                    ],
                )
            )

    result = await VideoHarness(media=FakeMediaPort(), model=UnsupportedModel()).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize the demonstration"),
        HarnessPolicy(output_dir=tmp_path / "unsupported-run"),
    )

    assert result.terminal_state.value == "PARTIAL"
    assert result.verification is not None
    assert "referenced_evidence_exists" in result.verification.failed_gates


@pytest.mark.asyncio
async def test_harness_marks_provider_errors_as_failed(tmp_path) -> None:
    class FailingModel:
        async def analyze_evidence(self, evidence, goal: VideoGoal) -> ModelResponse:
            del evidence, goal
            raise ProviderError("malformed response")

    result = await VideoHarness(media=FakeMediaPort(), model=FailingModel()).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize the demonstration"),
        HarnessPolicy(output_dir=tmp_path / "failed-run"),
    )

    assert result.terminal_state.value == "FAILED"


@pytest.mark.asyncio
async def test_harness_marks_model_call_budget_exhaustion_as_exhausted(tmp_path) -> None:
    result = await VideoHarness(media=FakeMediaPort(), model=FakeModel()).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize the demonstration"),
        HarnessPolicy(max_model_calls=0, output_dir=tmp_path / "exhausted-run"),
    )

    assert result.terminal_state.value == "EXHAUSTED"


@pytest.mark.asyncio
async def test_agentic_harness_uses_only_planned_audio_acquisition(tmp_path) -> None:
    """Adding an implicit visual acquisition to an audio-only plan must fail this test."""
    media = FakeMediaPort(has_audio=True)
    agent = ScriptedAgentModel(
        [
            AgentDecision(
                kind="tool_calls",
                calls=(ToolCallRequest(name="transcribe_audio", arguments={}),),
            ),
            AgentDecision(
                kind="final",
                output={
                    "summary": "Grounded.",
                    "claims": [
                        {"text": "Grounded.", "evidence": [{"evidence_id": "transcript-001"}]}
                    ],
                    "required_sections": {},
                },
            ),
        ]
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    result = await VideoHarness(
        media=media,
        model=FakeModel(),
        recognizer=FakeRecognizer(),
        planner=agent,
    ).run(
        VideoSource(path=source_path),
        VideoGoal(objective="What was said?"),
        HarnessPolicy(tool_mode="agentic", output_dir=tmp_path / "agentic-run"),
    )

    assert agent.plan_tools_calls == 0, "legacy one-shot plan_tools must never be used"
    assert media.audio_calls == [(0.0, 10.0)]
    assert media.visual_candidate_calls == 0
    assert result.terminal_state.value == "SUCCEEDED"
    events = [
        json.loads(line)
        for line in (tmp_path / "agentic-run" / "events.jsonl").read_text().splitlines()
    ]
    completed_tools = [
        event["payload"]["name"]
        for event in events
        if event.get("event_type") == "tool.call.completed"
    ]
    assert completed_tools == ["transcribe_audio"]
    assert result.result is not None
    referenced = [
        reference.evidence_id for claim in result.result.claims for reference in claim.evidence
    ]
    assert referenced == ["transcript-001"]
    assert result.verification is not None
    assert result.verification.passed is True


@pytest.mark.asyncio
async def test_fixed_harness_default_does_not_request_agentic_plan(tmp_path) -> None:
    """Changing the default fixed behavior to planner-controlled must fail this test."""
    media = FakeMediaPort()
    result = await VideoHarness(media=media, model=FakeModel()).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="Summarize"),
        HarnessPolicy(output_dir=tmp_path / "fixed-run"),
    )

    assert result.terminal_state.value == "SUCCEEDED"
    assert media.visual_candidate_calls == 1


class SegmentedMediaPort(FakeMediaPort):
    """A port that can also cut compressed segments, as the real FFmpeg port does."""

    def __init__(self) -> None:
        super().__init__(has_audio=True)
        self.segment_calls = 0

    async def extract_audio_segments(
        self, source: Path, output_dir: Path, *, start_seconds=0.0, end_seconds=None, **options
    ):
        from vidsnap.video.audio import AudioSegment

        del source, options
        self.segment_calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        segments = []
        for index, payload in enumerate((b"mp3-one", b"mp3-two")):
            path = output_dir / f"segment-{index:03d}.mp3"
            path.write_bytes(payload)
            segments.append(AudioSegment(path, index, "mp3", len(payload)))
        return segments


class CompressedRecognizer:
    accepts_compressed_audio = True

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        self.calls.append((audio_bytes, mime_type))
        return f"part {len(self.calls)}"


def _events(run_path: Path) -> list[dict]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


@pytest.mark.asyncio
async def test_fixed_harness_sends_compressed_segments_and_traces_what_was_sent(tmp_path) -> None:
    media = SegmentedMediaPort()
    recognizer = CompressedRecognizer()
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    result = await VideoHarness(media=media, model=FakeModel(), recognizer=recognizer).run(
        VideoSource(path=source_path),
        VideoGoal(objective="What was said?"),
        HarnessPolicy(output_dir=tmp_path / "run"),
    )

    assert result.terminal_state.value == "SUCCEEDED"
    assert media.segment_calls == 1 and media.audio_calls == []  # no WAV was extracted
    assert recognizer.calls == [(b"mp3-one", "audio/mpeg"), (b"mp3-two", "audio/mpeg")]
    transcript = json.loads((tmp_path / "run" / "evidence" / "transcript-001.json").read_text())
    assert transcript["content"] == "part 1\npart 2"
    (phase,) = [
        e
        for e in _events(tmp_path / "run")
        if e["phase"] == "transcribe_audio" and e["event_type"] == "phase.completed"
    ]
    assert phase["payload"]["audio_format"] == "mp3"
    assert phase["payload"]["audio_segments"] == 2
    assert phase["payload"]["audio_bytes"] == 14


@pytest.mark.asyncio
async def test_fixed_harness_keeps_wav_for_a_recognizer_that_does_not_take_compressed_audio(
    tmp_path,
) -> None:
    media = SegmentedMediaPort()  # could segment, but the recognizer never asked for it
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    result = await VideoHarness(media=media, model=FakeModel(), recognizer=FakeRecognizer()).run(
        VideoSource(path=source_path),
        VideoGoal(objective="What was said?"),
        HarnessPolicy(output_dir=tmp_path / "run"),
    )

    assert result.terminal_state.value == "SUCCEEDED"
    assert media.segment_calls == 0 and media.audio_calls == [(0.0, 10.0)]


@pytest.mark.asyncio
async def test_legacy_transcribe_step_uses_the_same_segments_and_trace_summary(tmp_path) -> None:
    from vidsnap.contracts.loopspec import default_loop_spec
    from vidsnap.harness import _RunContext
    from vidsnap.loop.run_bundle import RunBundle
    from vidsnap.loop.state_machine import LoopController

    harness = VideoHarness(media=SegmentedMediaPort(), model=FakeModel())
    recognizer = CompressedRecognizer()
    bundle = RunBundle.create(tmp_path / "run", loop_spec=default_loop_spec(), provider_url="x://y")
    policy = HarnessPolicy(output_dir=tmp_path / "run")
    context = _RunContext(
        source=VideoSource(path=tmp_path / "input.mp4"),
        goal=VideoGoal(objective="What was said?"),
        policy=policy,
        controller=LoopController(policy, max_repair_rounds=1),
        bundle=bundle,
        media=harness.media,
        model=FakeModel(),
        recognizer=recognizer,
        sampler=harness.sampler,
        planner=None,
        probe=MediaProbe(duration_seconds=10, fps=24, width=640, height=360, has_audio=True),
    )

    await harness._transcribe_audio(context)

    assert [mime for _, mime in recognizer.calls] == ["audio/mpeg", "audio/mpeg"]
    assert context.evidence[0].content == "part 1\npart 2"
    (phase,) = [e for e in _events(tmp_path / "run") if e["phase"] == "transcribe_audio"]
    assert phase["payload"]["status"] == "captured" and phase["payload"]["audio_segments"] == 2
