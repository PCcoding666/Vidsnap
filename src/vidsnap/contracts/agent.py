"""Strict contracts for agent decisions and provider-reported usage."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from vidsnap.contracts.models import StrictModel


class ToolCallRequest(StrictModel):
    """One model-requested tool invocation with bounded, typed arguments."""

    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class AgentDecision(StrictModel):
    """Exactly one next step for the harness: bounded tool calls or a final answer."""

    kind: Literal["tool_calls", "final"]
    calls: tuple[ToolCallRequest, ...] = Field(default=(), max_length=2)
    output: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def require_one_branch(self) -> AgentDecision:
        if self.kind == "tool_calls" and (not self.calls or self.output is not None):
            raise ValueError("tool_calls requires calls and forbids output")
        if self.kind == "final" and (self.calls or self.output is None):
            raise ValueError("final requires output and forbids calls")
        return self


class ProviderUsage(StrictModel):
    """Structured provider counters; reported=False marks unreported, not zero."""

    model_calls: int = Field(default=0, ge=0)
    input_bytes: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reported: bool = True

    def __add__(self, other: object) -> ProviderUsage:
        if not isinstance(other, ProviderUsage):
            raise TypeError("ProviderUsage can only be added to ProviderUsage")
        return ProviderUsage(
            model_calls=self.model_calls + other.model_calls,
            input_bytes=self.input_bytes + other.input_bytes,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reported=self.reported and other.reported,
        )
