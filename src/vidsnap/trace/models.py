"""Strict, secret-free models for projected run traces."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, JsonValue

from vidsnap.contracts.models import StrictModel
from vidsnap.loop.events import EventStatus, EventUsage

TraceLane = Literal["input", "model", "tools", "verifier"]


class FrozenProjectionModel(StrictModel):
    """Base for immutable projection models; projection data never mutates."""

    model_config = ConfigDict(frozen=True)


class TraceItem(StrictModel):
    """One ledger event projected through the sanitizing truth-only boundary.

    Values are the recorded truth as it passed the projection boundary; the
    projection is not guaranteed to be byte-for-byte identical to the raw
    ledger, because sensitive keys and exposing values are removed here.
    """

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


class TraceOverview(FrozenProjectionModel):
    """Run-level overview projected from recorded truth only."""

    goal: str | None = None
    input_sha256: str | None = None
    status: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    provider: str | None = None
    recipe: str | None = None


class TraceBudgetCounter(FrozenProjectionModel):
    """One consumed/allowed pair projected from the recorded budget snapshot."""

    used: int | None = Field(default=None, ge=0)
    limit: int | None = Field(default=None, ge=0)


class TraceBudget(FrozenProjectionModel):
    """Budget projection with one counter per harness limit."""

    model_calls: TraceBudgetCounter = Field(default_factory=TraceBudgetCounter)
    evidence_frames: TraceBudgetCounter = Field(default_factory=TraceBudgetCounter)
    iterations: TraceBudgetCounter = Field(default_factory=TraceBudgetCounter)
    runtime_ms: TraceBudgetCounter = Field(default_factory=TraceBudgetCounter)


class TraceEvidence(FrozenProjectionModel):
    """One evidence item projected without provider or media identity."""

    evidence_id: str | None = None
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    modality: str | None = None
    content_preview: str | None = Field(default=None, max_length=280)
    source: str | None = None
    speaker: str | None = None
    frame: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class TraceClaim(FrozenProjectionModel):
    """One claim projected with its evidence references and review status."""

    text: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    verification_result: str | None = None
    editorial_status: str | None = None


class TraceDocument(StrictModel):
    """A read-only projection of one run; it never carries provider identity."""

    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    terminal_state: str | None = Field(default=None, min_length=1, max_length=64)
    summary_only: bool = False
    items: list[TraceItem] = Field(default_factory=list)
    duration_ms: int | None = Field(default=None, ge=0)
    usage: EventUsage | None = None
    limitations: list[str] = Field(default_factory=list)
    overview: TraceOverview = Field(default_factory=TraceOverview)
    budget: TraceBudget = Field(default_factory=TraceBudget)
    evidence: list[TraceEvidence] = Field(default_factory=list)
    claims: list[TraceClaim] = Field(default_factory=list)
