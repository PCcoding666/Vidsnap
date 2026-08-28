"""Deterministic zero-dependency mock provider for offline harness runs."""

from __future__ import annotations

from collections.abc import Sequence

from vidsnap.contracts import Evidence, ToolPlan, VideoAnalysisResult, VideoGoal
from vidsnap.contracts.agent import AgentDecision, ProviderUsage
from vidsnap.contracts.tool_plan import AcquisitionTool
from vidsnap.providers.base import (
    AgentDecisionResponse,
    AgentStepRequest,
    ModelResponse,
    ProviderIdentity,
    ToolPlanResponse,
)
from vidsnap.video.probe import MediaProbe

_MOCK_IDENTITY = ProviderIdentity(id="mock", model="mock", base_url="offline://mock")


class MockProvider:
    """A deterministic, offline provider that ignores every model input."""

    def __init__(self) -> None:
        """Accept no configuration; the mock is fully self-contained."""

    @property
    def identity(self) -> ProviderIdentity:
        """The read-only fixed identity used by discovery and selection."""
        return _MOCK_IDENTITY

    async def analyze_evidence(
        self,
        evidence: Sequence[Evidence],
        goal: VideoGoal,
    ) -> ModelResponse:
        """Produce a schema-valid result for typed, captured evidence."""
        del evidence, goal
        return ModelResponse(
            result=VideoAnalysisResult(summary="mock", claims=[]),
            input_tokens=3,
            output_tokens=5,
            usage_reported=True,
        )

    async def plan_tools(self, probe: MediaProbe, goal: VideoGoal) -> ToolPlanResponse:
        """Choose a bounded subset of the two acquisition tools."""
        del goal
        tools: tuple[AcquisitionTool, ...] = (
            ("transcribe_audio",) if probe.has_audio else ("sample_evidence",)
        )
        return ToolPlanResponse(
            plan=ToolPlan(tools=tools),
            input_tokens=3,
            output_tokens=5,
            input_bytes=0,
            usage_reported=True,
        )

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        """Return exactly one bounded tool-call batch or one final answer."""
        del request
        return AgentDecisionResponse(
            decision=AgentDecision(kind="final", output={"summary": "mock"}),
            usage=ProviderUsage(
                model_calls=1,
                input_tokens=3,
                output_tokens=5,
                reported=True,
            ),
        )
