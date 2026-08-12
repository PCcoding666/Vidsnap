"""Provider ports that keep model calls behind typed, bounded interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from vidsnap.contracts import Evidence, ToolPlan, VideoAnalysisResult, VideoGoal
from vidsnap.video.probe import MediaProbe


class ProviderError(RuntimeError):
    """Raised for an unavailable or malformed model-provider response."""


class ProviderUnavailable(ProviderError):
    """Raised when a local credential or provider dependency is unavailable."""


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """A parsed, structured model result plus usage reported by the provider."""

    result: VideoAnalysisResult
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ToolPlanResponse:
    """A validated acquisition plan plus provider-reported usage."""

    plan: ToolPlan
    input_tokens: int = 0
    output_tokens: int = 0


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
