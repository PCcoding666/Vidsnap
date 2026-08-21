"""Video-analysis task adapter: strict output parsing and verifier reuse."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vidsnap.contracts import Evidence, VideoAnalysisResult, VideoGoal
from vidsnap.providers.base import ModelResponse
from vidsnap.tasks import TaskVerification, VideoAnalysisTaskAdapter
from vidsnap.video.probe import MediaProbe


def make_probe() -> MediaProbe:
    return MediaProbe(duration_seconds=10, fps=24, width=640, height=360, has_audio=False)


def test_video_task_adapter_parses_strict_output_and_reuses_verifier() -> None:
    adapter = VideoAnalysisTaskAdapter(VideoGoal(objective="Summarize"))
    payload = {
        "summary": "A person moves.",
        "claims": [{"text": "A person moves.", "evidence": [{"evidence_id": "frame-001"}]}],
        "required_sections": {},
    }
    output = adapter.parse_final(payload)
    evidence = [Evidence(id="frame-001", start_seconds=1, end_seconds=1, modality="frame")]
    verification = adapter.verify(output, evidence=evidence, probe=make_probe())
    assert isinstance(verification, TaskVerification)
    assert verification.passed is True
    assert all(verification.gates.values())


def test_video_task_adapter_rejects_unknown_output_fields() -> None:
    adapter = VideoAnalysisTaskAdapter(VideoGoal(objective="Summarize"))
    payload = {"summary": "No claims.", "claims": [], "required_sections": {}}
    with pytest.raises(ValidationError):
        adapter.parse_final({**payload, "raw_reasoning": "hidden"})


def test_video_task_adapter_surfaces_failed_gates_and_targeted_windows() -> None:
    adapter = VideoAnalysisTaskAdapter(VideoGoal(objective="Summarize"))
    output = adapter.parse_final(
        {
            "summary": "A claim without evidence.",
            "claims": [{"text": "unsupported", "evidence": [{"evidence_id": "frame-999"}]}],
            "required_sections": {},
        }
    )
    verification = adapter.verify(output, evidence=[], probe=make_probe())
    assert verification.passed is False
    assert verification.gates["referenced_evidence_exists"] is False
    assert verification.gates["claims_are_supported"] is False
    assert verification.gates["timestamps_in_bounds"] is True


def test_video_task_adapter_requires_goal_sections_in_verification() -> None:
    adapter = VideoAnalysisTaskAdapter(
        VideoGoal(objective="Summarize", required_sections=("timeline",))
    )
    output = adapter.parse_final(
        {
            "summary": "Grounded.",
            "claims": [{"text": "Grounded.", "evidence": [{"evidence_id": "frame-001"}]}],
            "required_sections": {},
        }
    )
    evidence = [Evidence(id="frame-001", start_seconds=1, end_seconds=1, modality="frame")]
    verification = adapter.verify(output, evidence=evidence, probe=make_probe())
    assert verification.passed is False
    assert verification.gates["required_sections_covered"] is False


@pytest.mark.asyncio
async def test_video_task_adapter_maps_final_model_usage() -> None:
    class FakeVideoModel:
        async def analyze_evidence(self, evidence, goal):
            del evidence, goal
            return ModelResponse(
                result=VideoAnalysisResult(summary="Done.", claims=[]),
                input_tokens=9,
                output_tokens=2,
                usage_reported=True,
            )

    adapter = VideoAnalysisTaskAdapter(VideoGoal(objective="Summarize"))
    output, usage = await adapter.request_final(FakeVideoModel(), evidence=(), probe=make_probe())
    assert output.summary == "Done."
    assert usage.input_tokens == 9
    assert usage.output_tokens == 2
    assert usage.reported is True


@pytest.mark.asyncio
async def test_video_task_adapter_marks_unreported_usage() -> None:
    class FakeVideoModel:
        async def analyze_evidence(self, evidence, goal):
            del evidence, goal
            return ModelResponse(result=VideoAnalysisResult(summary="Done.", claims=[]))

    adapter = VideoAnalysisTaskAdapter(VideoGoal(objective="Summarize"))
    _, usage = await adapter.request_final(FakeVideoModel(), evidence=(), probe=make_probe())
    assert usage.reported is False
