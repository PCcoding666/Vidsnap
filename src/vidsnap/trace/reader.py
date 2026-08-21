"""Strict reader that projects recorded RunBundle ledgers into TraceDocuments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from vidsnap.loop.events import EventUsage, RunEvent
from vidsnap.trace.models import TraceDocument, TraceItem, TraceLane

_LANE_PREFIXES: tuple[tuple[str, TraceLane], ...] = (
    ("model.request", "model"),
    ("agent.decision", "model"),
    ("tool.call", "tools"),
    ("evidence.added", "tools"),
    ("verifier", "verifier"),
    ("repair", "verifier"),
    ("terminal", "verifier"),
    ("run", "input"),
    ("probe", "input"),
)
_USAGE_FIELDS = frozenset(EventUsage.model_fields)


def read_trace(path: Path) -> TraceDocument:
    """Read one RunBundle or legacy result directory without inventing data."""
    manifest = _load_manifest(path)
    if manifest.get("trace_schema") is None:
        return _read_summary_only(path, manifest)
    return _read_step_events(path, manifest)


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("run manifest is missing or unreadable") from error
    if not isinstance(loaded, dict):
        raise ValueError("run manifest is missing or unreadable")
    return loaded


def _read_step_events(path: Path, manifest: dict[str, Any]) -> TraceDocument:
    events = _load_events(path / "events.jsonl")
    pending: dict[tuple[str, str], RunEvent] = {}
    items: list[TraceItem] = []
    usage_total: EventUsage | None = None
    run_duration_ms: int | None = None

    for event in events:
        if event.usage is not None:
            usage_total = event.usage if usage_total is None else usage_total + event.usage
        event_type = event.event_type
        if event_type is None:
            continue
        lane = _lane_for(event_type)
        if lane is None:
            continue

        duration_ms: int | None = None
        base_type = _base_type(event_type)
        if event.status == "started":
            if event.correlation_id is not None:
                pending[(base_type, event.correlation_id)] = event
        elif event.correlation_id is not None:
            start = pending.pop((base_type, event.correlation_id), None)
            if (
                start is not None
                and start.monotonic_offset_ms is not None
                and event.monotonic_offset_ms is not None
            ):
                duration_ms = event.monotonic_offset_ms - start.monotonic_offset_ms
                if base_type == "run":
                    run_duration_ms = duration_ms

        items.append(
            TraceItem(
                sequence=event.sequence,
                phase=event.phase,
                event_type=event_type,
                lane=lane,
                offset_ms=event.monotonic_offset_ms,
                duration_ms=duration_ms if duration_ms is not None and duration_ms >= 0 else None,
                status=event.status,
                payload=event.payload,
                usage=event.usage,
            )
        )

    return TraceDocument(
        run_id=_optional_str(manifest.get("run_id")),
        terminal_state=_optional_str(manifest.get("terminal_state")),
        summary_only=False,
        items=items,
        duration_ms=run_duration_ms,
        usage=usage_total,
    )


def _read_summary_only(path: Path, manifest: dict[str, Any]) -> TraceDocument:
    return TraceDocument(
        run_id=_optional_str(manifest.get("run_id")),
        terminal_state=_optional_str(manifest.get("terminal_state")),
        summary_only=True,
        usage=_aggregate_outcome_usage(path / "outcomes.jsonl"),
        limitations=["step-level events were not recorded"],
    )


def _load_events(ledger_path: Path) -> list[RunEvent]:
    events: list[RunEvent] = []
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return events
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("trace ledger is unreadable") from error
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            events.append(RunEvent.model_validate(data))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            raise ValueError(f"invalid trace ledger entry at line {line_number}") from error
    return events


def _aggregate_outcome_usage(outcomes_path: Path) -> EventUsage | None:
    try:
        lines = outcomes_path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return None
    total: EventUsage | None = None
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            outcome = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid outcome entry at line {line_number}") from error
        if not isinstance(outcome, dict):
            continue
        usage = outcome.get("usage")
        if not isinstance(usage, dict):
            continue
        counters = {
            key: value
            for key, value in usage.items()
            if key in _USAGE_FIELDS
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        }
        entry = EventUsage.model_validate(counters)
        total = entry if total is None else total + entry
    return total


def _lane_for(event_type: str) -> TraceLane | None:
    for prefix, lane in _LANE_PREFIXES:
        if event_type == prefix or event_type.startswith(f"{prefix}."):
            return lane
    return None


def _base_type(event_type: str) -> str:
    base_type, _, _suffix = event_type.rpartition(".")
    return base_type or event_type


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
