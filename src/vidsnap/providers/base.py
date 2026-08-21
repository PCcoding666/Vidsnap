"""Provider ports that keep model calls behind typed, bounded interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import JsonValue

from vidsnap.contracts import Evidence, ToolPlan, VideoAnalysisResult, VideoGoal
from vidsnap.contracts.agent import AgentDecision, ProviderUsage
from vidsnap.video.probe import MediaProbe


class ProviderError(RuntimeError):
    """Raised for an unavailable or malformed model-provider response."""


class ProviderUnavailable(ProviderError):
    """Raised when a local credential or provider dependency is unavailable."""


class AgentDecisionFormatError(ProviderError):
    """Raised when a successful agent-decision response body is not a valid decision."""


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """A parsed, structured model result plus usage reported by the provider."""

    result: VideoAnalysisResult
    input_tokens: int = 0
    output_tokens: int = 0
    usage_reported: bool = False


@dataclass(frozen=True, slots=True)
class ToolPlanResponse:
    """A validated acquisition plan plus provider-reported usage."""

    plan: ToolPlan
    input_tokens: int = 0
    output_tokens: int = 0
    input_bytes: int = 0
    usage_reported: bool = False


class ToolPlanningPort(Protocol):
    """The only model operation allowed to choose acquisition tools."""

    async def plan_tools(self, probe: MediaProbe, goal: VideoGoal) -> ToolPlanResponse:
        """Choose a bounded subset of the two acquisition tools."""


class VideoModelPort(Protocol):
    """The only model operation the harness may invoke."""

    async def analyze_evidence(
        self,
        evidence: Sequence[Evidence],
        goal: VideoGoal,
    ) -> ModelResponse:
        """Produce a schema-valid result for typed, captured evidence."""


@dataclass(frozen=True, slots=True)
class AgentStepRequest:
    """Everything one bounded agent decision may observe; nothing it may control."""

    goal: VideoGoal
    probe: MediaProbe
    evidence: tuple[Evidence, ...]
    tool_results: tuple[dict[str, JsonValue], ...]
    tool_schemas: tuple[dict[str, JsonValue], ...]
    output_schema: dict[str, JsonValue]
    remaining_model_calls: int
    remaining_tool_calls: int
    remaining_frames: int
    verifier_feedback: dict[str, JsonValue] | None = None
    format_repair: bool = False


@dataclass(frozen=True, slots=True)
class AgentDecisionResponse:
    """One strict agent decision plus provider-reported usage."""

    decision: AgentDecision
    usage: ProviderUsage


class AgentModelPort(Protocol):
    """The only model operation allowed to steer the multi-turn harness loop."""

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        """Return exactly one bounded tool-call batch or one final answer."""
