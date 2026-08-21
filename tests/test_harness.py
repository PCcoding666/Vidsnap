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
