"""Paired, duration-measured trace spans for one harness run."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import JsonValue

from vidsnap.contracts.agent import ProviderUsage
from vidsnap.loop.events import EventStatus, EventUsage, RunEvent
from vidsnap.loop.run_bundle import RunBundle

_BASE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


@dataclass(frozen=True, slots=True)
class TraceSpan:
    """An open span whose completion event must share its correlation ID."""

    base_type: str
    phase: str
    event_id: str
    correlation_id: str
    parent_event_id: str | None
    turn: int | None
    step: int | None
    started_offset_ms: int


class TraceRecorder:
    """Writes real started/completed event pairs into a RunBundle ledger."""

    def __init__(self, bundle: RunBundle, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._bundle = bundle
        self._clock = clock
        self._origin_seconds: float | None = None
        self._finished_event_ids: set[str] = set()

    def start(
        self,
        base_type: str,
        *,
        phase: str,
        turn: int | None = None,
        step: int | None = None,
        payload: dict[str, JsonValue] | None = None,
        parent_event_id: str | None = None,
    ) -> TraceSpan:
        """Append one `<base_type>.started` event and return the open span."""
        if not _BASE_TYPE_PATTERN.match(base_type):
            raise ValueError(f"unsupported trace base type: {base_type}")
        offset_ms = self._current_offset_ms()
        event = self._bundle.append_event(
            phase,
            payload,
            event_id=uuid.uuid4().hex,
            event_type=f"{base_type}.started",
            turn=turn,
            step=step,
            parent_event_id=parent_event_id,
            correlation_id=uuid.uuid4().hex,
            monotonic_offset_ms=offset_ms,
            status="started",
        )
        assert event.event_id is not None
        assert event.correlation_id is not None
        return TraceSpan(
            base_type=base_type,
            phase=phase,
            event_id=event.event_id,
            correlation_id=event.correlation_id,
            parent_event_id=parent_event_id,
            turn=turn,
            step=step,
            started_offset_ms=offset_ms,
        )

    def finish(
        self,
        span: TraceSpan,
        *,
        status: EventStatus,
        phase: str | None = None,
        payload: dict[str, JsonValue] | None = None,
        usage: ProviderUsage | None = None,
    ) -> RunEvent:
        """Append the paired terminal event with a real measured duration."""
        if status == "started":
            raise ValueError("finish() requires a terminal span status")
        if span.event_id in self._finished_event_ids:
            raise ValueError(f"span is already finished: {span.event_id}")
        self._finished_event_ids.add(span.event_id)
        offset_ms = self._current_offset_ms()
        return self._bundle.append_event(
            phase if phase is not None else span.phase,
            payload,
            event_id=uuid.uuid4().hex,
            event_type=f"{span.base_type}.{status}",
            turn=span.turn,
            step=span.step,
            parent_event_id=span.parent_event_id,
            correlation_id=span.correlation_id,
            monotonic_offset_ms=offset_ms,
            status=status,
            usage=_event_usage(usage),
            duration_ms=offset_ms - span.started_offset_ms,
        )

    def _current_offset_ms(self) -> int:
        now = self._clock()
        if self._origin_seconds is None:
            self._origin_seconds = now
        return int(round((now - self._origin_seconds) * 1000))


def _event_usage(usage: ProviderUsage | None) -> EventUsage | None:
    if usage is None:
        return None
    return EventUsage(
        model_calls=usage.model_calls,
        input_bytes=usage.input_bytes,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        provider_reported=usage.reported,
    )
