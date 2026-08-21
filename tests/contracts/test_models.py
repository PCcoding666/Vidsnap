"""Public data-contract validation tests."""

import json
from importlib.resources import files

import pytest

from vidsnap.contracts import (
    Claim,
    EvidenceReference,
    HarnessPolicy,
    VideoAnalysisResult,
    VideoGoal,
)


def test_claim_requires_a_reference_to_captured_evidence() -> None:
    with pytest.raises(ValueError):
        Claim(text="The speaker demonstrates a workflow", evidence=[])

    claim = Claim(
        text="The speaker demonstrates a workflow",
        evidence=[EvidenceReference(evidence_id="ev-1")],
    )

    assert claim.evidence[0].evidence_id == "ev-1"


def test_policy_cannot_expand_the_approved_resource_envelope() -> None:
    with pytest.raises(ValueError):
        HarnessPolicy(max_model_calls=13)


def test_policy_bounds_model_visible_tool_calls() -> None:
    assert HarnessPolicy().max_tool_calls == 6
    assert HarnessPolicy(max_tool_calls=0).max_tool_calls == 0
    with pytest.raises(ValueError):
        HarnessPolicy(max_tool_calls=7)
    with pytest.raises(ValueError):
        HarnessPolicy(max_tool_calls=-1)


def test_models_reject_unknown_input_and_emit_the_versioned_result_schema() -> None:
    with pytest.raises(ValueError):
        VideoGoal(objective="Summarize the demonstration", arbitrary_prompt="ignored")

    result = VideoAnalysisResult(summary="A concise grounded summary.", claims=[])
    assert result.model_dump(mode="json")["summary"] == "A concise grounded summary."

    schema = json.loads(
        files("vidsnap.contracts.schemas").joinpath("video_analysis.v1.json").read_text()
    )
    assert schema["$id"] == "vidsnap.video-analysis/v1"
    assert schema["additionalProperties"] is False
