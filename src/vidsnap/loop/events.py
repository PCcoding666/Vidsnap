"""Typed, append-only events for a single harness run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from vidsnap.contracts.models import StrictModel

EventStatus = Literal["started", "completed", "failed", "blocked", "skipped"]


class EventUsage(StrictModel):
    """Safe, structured usage counters attached to a completed or failed event."""

    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    evidence_frames: int = Field(default=0, ge=0)
    input_bytes: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    provider_reported: bool = True

    def __add__(self, other: object) -> EventUsage:
        if not isinstance(other, EventUsage):
            raise TypeError("EventUsage can only be added to EventUsage")
        return EventUsage(
            model_calls=self.model_calls + other.model_calls,
            tool_calls=self.tool_calls + other.tool_calls,
            evidence_frames=self.evidence_frames + other.evidence_frames,
            input_bytes=self.input_bytes + other.input_bytes,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            provider_reported=self.provider_reported and other.provider_reported,
        )


class RunEvent(StrictModel):
    """One timestamped state transition or observation in a RunBundle."""

    sequence: int = Field(ge=1)
    phase: str = Field(min_length=1, max_length=128)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str | None = Field(default=None, min_length=1, max_length=64)
    event_type: str | None = Field(default=None, min_length=1, max_length=128)
    turn: int | None = Field(default=None, ge=1)
    step: int | None = Field(default=None, ge=1)
    parent_event_id: str | None = Field(default=None, min_length=1, max_length=64)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=64)
    monotonic_offset_ms: int | None = Field(default=None, ge=0)
    status: EventStatus | None = None
    usage: EventUsage | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_utc_timestamp(self) -> RunEvent:
        utc_offset = self.occurred_at.utcoffset()
        if self.occurred_at.tzinfo is None or utc_offset is None:
            raise ValueError("occurred_at must include a UTC timezone")
        if utc_offset.total_seconds() != 0:
            raise ValueError("occurred_at must be expressed in UTC")
        return self

    def to_json(self) -> str:
        """Serialize the event deterministically for a JSONL ledger."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
