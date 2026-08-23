"""Model-selected acquisition plan contract tests."""

import pytest

from vidsnap.contracts import ToolPlan


def test_tool_plan_rejects_duplicate_and_non_acquisition_skills() -> None:
    """A planner cannot expand the safe acquisition surface or repeat a paid call."""
    assert ToolPlan(tools=("transcribe_audio",)).tools == ("transcribe_audio",)

    with pytest.raises(ValueError, match="duplicate"):
        ToolPlan(tools=("sample_evidence", "sample_evidence"))

    with pytest.raises(ValueError):
        ToolPlan(tools=("verify_claims",))
