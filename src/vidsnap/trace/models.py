"""Strict, secret-free models for projected run traces."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from vidsnap.contracts.models import StrictModel
from vidsnap.loop.events import EventStatus, EventUsage

TraceLane = Literal["input", "model", "tools", "verifier"]


class TraceItem(StrictModel):
    """One recorded event projected exactly as it was written to the ledger."""

    sequence: int = Field(ge=1)
    phase: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    lane: TraceLane
    turn: int | None = Field(default=None, ge=1)
    step: int | None = Field(default=None, ge=1)
    offset_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    status: EventStatus | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    usage: EventUsage | None = None


class TraceDocument(StrictModel):
    """A read-only projection of one run; it never carries provider identity."""

    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    terminal_state: str | None = Field(default=None, min_length=1, max_length=64)
    summary_only: bool = False
    items: list[TraceItem] = Field(default_factory=list)
    duration_ms: int | None = Field(default=None, ge=0)
    usage: EventUsage | None = None
    limitations: list[str] = Field(default_factory=list)
