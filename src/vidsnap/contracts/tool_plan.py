"""Strict contract for model-selected evidence acquisition."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from vidsnap.contracts.models import StrictModel

AcquisitionTool = Literal["transcribe_audio", "sample_evidence"]
ToolMode = Literal["fixed", "agentic"]


class ToolPlan(StrictModel):
    """A bounded, unique subset of the only model-selectable tools."""

    tools: tuple[AcquisitionTool, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def reject_duplicate_tools(self) -> ToolPlan:
        """Reject repeated paid work even when it uses an allowed tool."""
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("tool plan contains duplicate tools")
        return self
