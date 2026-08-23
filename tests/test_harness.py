"""End-to-end bounded harness behavior with local fake ports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vidsnap.contracts import (
    Claim,
    EvidenceReference,
    HarnessPolicy,
    ToolPlan,
    VideoAnalysisResult,
    VideoGoal,
    VideoSource,
)
from vidsnap.harness import VideoHarness
from vidsnap.providers.base import (
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

    async def extract_audio(self, source: Path, output_path: Path) -> Path:
        del source
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
    result = await VideoHarness(
        media=media,
        model=FakeModel(),
        recognizer=FakeRecognizer(),
        planner=FakePlanner(ToolPlan(tools=("transcribe_audio",))),
    ).run(
        VideoSource(path=tmp_path / "input.mp4"),
        VideoGoal(objective="What was said?"),
        HarnessPolicy(tool_mode="agentic", output_dir=tmp_path / "agentic-run"),
    )

    events = [
        json.loads(line)
        for line in (tmp_path / "agentic-run" / "events.jsonl").read_text().splitlines()
    ]
    tool_plan_event = next(event for event in events if event["phase"] == "tool_plan")
    assert tool_plan_event["payload"] == {
        "input_tokens": 11,
        "mode": "agentic",
        "output_tokens": 3,
        "selected_tools": ["transcribe_audio"],
    }
    assert media.visual_candidate_calls == 0
    assert result.terminal_state.value == "SUCCEEDED"


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
