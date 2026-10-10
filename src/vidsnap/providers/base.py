"""Provider ports that keep model calls behind typed, bounded interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, get_args, runtime_checkable

from pydantic import JsonValue

from vidsnap.contracts import Evidence, ToolPlan, VideoAnalysisResult, VideoGoal
from vidsnap.contracts.agent import AgentDecision, ProviderUsage
from vidsnap.video.probe import MediaProbe

FailureCategory = Literal[
    "connect_timeout",
    "read_timeout",
    "write_timeout",
    "pool_timeout",
    "connection_error",
    "transport_error",
    "http_error",
    "request_deadline",
    "invalid_response",
    "cancelled",
    "run_deadline",
    "provider_error",
]


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """Allow-listed failure facts, never raw exceptions, URLs or provider bodies."""

    category: FailureCategory
    http_status: int | None = None
    input_bytes: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.category not in get_args(FailureCategory):
            raise ValueError("unsupported provider failure category")
        for value in (self.http_status, self.input_bytes, self.input_tokens, self.output_tokens):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError("provider failure counters must be non-negative integers or null")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("invalid HTTP status")

    def as_payload(self) -> dict[str, JsonValue]:
        """Versioned additive trace metadata; missing measurements remain null."""
        return {
            "schema_version": "vidsnap.provider-failure/v1",
            "category": self.category,
            "http_status": self.http_status,
            "input_bytes": self.input_bytes,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class ProviderError(RuntimeError):
    """Raised for an unavailable or malformed model-provider response."""

    failure: ProviderFailure | None = None

    def __init__(self, message: str, *, failure: ProviderFailure | None = None) -> None:
        super().__init__(message)
        if failure is not None:
            self.failure = failure


class ProviderCancelledError(asyncio.CancelledError):
    """Preserve measured request facts while allowing cancellation to propagate."""

    def __init__(self, *, failure: ProviderFailure) -> None:
        super().__init__("provider call cancelled")
        self.failure = failure


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
    input_bytes: int = 0


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


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """The fixed, immutable identity a provider exposes to harness and discovery."""

    id: str
    model: str
    base_url: str


@runtime_checkable
class ProviderProtocol(AgentModelPort, ToolPlanningPort, VideoModelPort, Protocol):
    """Runtime conformance contract every complete bounded provider must satisfy."""

    @property
    def identity(self) -> ProviderIdentity:
        """The read-only fixed identity used by discovery and selection."""


@runtime_checkable
class ProviderPlugin(ProviderProtocol, Protocol):
    """The provider extension contract; any runtime-conforming provider qualifies."""
