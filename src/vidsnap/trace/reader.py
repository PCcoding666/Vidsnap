"""Strict reader that projects recorded RunBundle ledgers into TraceDocuments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import JsonValue, ValidationError

from vidsnap.contracts.models import Evidence, VideoAnalysisResult
from vidsnap.loop.events import EventUsage, RunEvent
from vidsnap.trace.models import (
    TraceBudget,
    TraceBudgetCounter,
    TraceClaim,
    TraceDocument,
    TraceEvidence,
    TraceItem,
    TraceLane,
    TraceOverview,
)

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
_REDACTED = "***REDACTED***"
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "credential",
    "password",
    "passwd",
    "cookie",
    "secret",
    "api_key",
    "apikey",
    "chain_of_thought",
    "internal_reasoning",
    "scratchpad",
    "thoughts",
    "header",
)
_SENSITIVE_EXACT_KEYS = frozenset({"env", "environ", "environment", "pat", "pwd", "auth"})
_TOKEN_USAGE_KEYS = frozenset(
    {
        "cached_tokens",
        "completion_tokens",
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "reasoning_tokens",
        "total_tokens",
    }
)
_QUERY_SECRET_PARTS = (
    "key=",
    "token=",
    "secret=",
    "password=",
    "signature=",
    "credential=",
)


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
    latest_budget_payload: dict[str, JsonValue] | None = None

    for event in events:
        if event.usage is not None:
            usage_total = event.usage if usage_total is None else usage_total + event.usage
        event_type = event.event_type
        if event_type is None:
            continue
        payload = _sanitize_payload(event.payload)
        if event_type == "budget.updated":
            latest_budget_payload = payload
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
                turn=event.turn,
                step=event.step,
                offset_ms=event.monotonic_offset_ms,
                duration_ms=duration_ms if duration_ms is not None and duration_ms >= 0 else None,
                status=event.status,
                payload=payload,
                usage=event.usage,
            )
        )

    evidence_projections, evidence_limitations = _project_evidence(path)
    claim_projections, claim_limitations = _project_claims(path)
    return TraceDocument(
        run_id=_optional_str(manifest.get("run_id")),
        terminal_state=_optional_str(manifest.get("terminal_state")),
        summary_only=False,
        items=items,
        duration_ms=run_duration_ms,
        usage=usage_total,
        limitations=[*evidence_limitations, *claim_limitations],
        overview=_build_overview(manifest, items, run_duration_ms),
        budget=_build_budget(manifest, latest_budget_payload, run_duration_ms),
        evidence=evidence_projections,
        claims=claim_projections,
    )


def _read_summary_only(path: Path, manifest: dict[str, Any]) -> TraceDocument:
    return TraceDocument(
        run_id=_optional_str(manifest.get("run_id")),
        terminal_state=_optional_str(manifest.get("terminal_state")),
        summary_only=True,
        usage=_aggregate_outcome_usage(path / "outcomes.jsonl"),
        limitations=["step-level events were not recorded"],
        overview=_build_overview(manifest, [], None),
        budget=_build_budget(manifest, None, None),
    )


def _sanitize_payload(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Project-boundary sanitizer: drop sensitive keys, redact exposing values."""
    cleaned: dict[str, JsonValue] = {}
    for key, item in payload.items():
        if _is_sensitive_key(key):
            continue
        cleaned[key] = _sanitize_value(item)
    return cleaned


def _sanitize_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        cleaned: dict[str, JsonValue] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                continue
            cleaned[str(key)] = _sanitize_value(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    """Match sensitive keys case-insensitively while preserving usage counters."""
    normalized = key.lower()
    if normalized in _TOKEN_USAGE_KEYS:
        return False
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
        return True
    return "reasoning" in normalized or "token" in normalized


def _redact_string(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith("/users/") or lowered.startswith("/home/"):
        return _REDACTED
    if "://" in value:
        authority = value.split("://", 1)[1].split("/", 1)[0]
        query = value.split("?", 1)[1] if "?" in value else ""
        if "@" in authority:
            return _REDACTED
        if any(part in query.lower() for part in _QUERY_SECRET_PARTS):
            return _REDACTED
    if "api_key=" in lowered or "authorization:" in lowered or "bearer " in lowered:
        return _REDACTED
    return value


def _build_overview(
    manifest: dict[str, Any],
    items: list[TraceItem],
    duration_ms: int | None,
) -> TraceOverview:
    goal: str | None = None
    input_sha256: str | None = None
    for item in items:
        if item.event_type == "run.started":
            goal = _optional_str(item.payload.get("goal"))
            input_sha256 = _optional_str(item.payload.get("input_sha256"))
            break
    return TraceOverview(
        goal=goal,
        input_sha256=input_sha256,
        status=_optional_str(manifest.get("terminal_state")),
        duration_ms=duration_ms,
        provider=_provider_marker(manifest),
        recipe=_recipe(manifest),
    )


def _provider_marker(manifest: dict[str, Any]) -> str:
    provider = manifest.get("provider")
    if isinstance(provider, dict):
        base_url = provider.get("base_url")
        if isinstance(base_url, str) and base_url:
            return "configured (identity redacted)"
    return "not recorded"


def _recipe(manifest: dict[str, Any]) -> str | None:
    loop_spec = manifest.get("loop_spec")
    if isinstance(loop_spec, dict):
        return _optional_str(loop_spec.get("id"))
    return None


def _build_budget(
    manifest: dict[str, Any],
    latest_budget_payload: dict[str, JsonValue] | None,
    duration_ms: int | None,
) -> TraceBudget:
    latest_used: dict[str, int | None] = {
        "model_calls": None,
        "evidence_frames": None,
        "iterations": None,
    }
    if latest_budget_payload is not None:
        for key in latest_used:
            latest_used[key] = _nonnegative_int(latest_budget_payload.get(key))
    resources = manifest.get("resources")
    resources = resources if isinstance(resources, dict) else {}
    return TraceBudget(
        model_calls=TraceBudgetCounter(
            used=latest_used["model_calls"],
            limit=_nonnegative_int(resources.get("max_model_calls")),
        ),
        evidence_frames=TraceBudgetCounter(
            used=latest_used["evidence_frames"],
            limit=_nonnegative_int(resources.get("max_evidence_frames")),
        ),
        iterations=TraceBudgetCounter(
            used=latest_used["iterations"],
            limit=_nonnegative_int(resources.get("max_iterations")),
        ),
        runtime_ms=TraceBudgetCounter(
            used=duration_ms,
            limit=_runtime_limit_ms(resources),
        ),
    )


def _runtime_limit_ms(resources: dict[str, Any]) -> int | None:
    max_wall_seconds = _nonnegative_int(resources.get("max_wall_seconds"))
    return max_wall_seconds * 1000 if max_wall_seconds is not None else None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _project_evidence(path: Path) -> tuple[list[TraceEvidence], list[str]]:
    """Project structured evidence files without ever reading artifact bytes."""
    evidence_projections: list[TraceEvidence] = []
    skipped = 0
    evidence_dir = path / "evidence"
    try:
        candidates = sorted(evidence_dir.glob("*.json"))
    except OSError:
        return [], ["evidence directory was unreadable; evidence was omitted"]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            evidence = Evidence.model_validate_json(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValidationError, ValueError):
            skipped += 1
            continue
        evidence_projections.append(
            TraceEvidence(
                evidence_id=evidence.id,
                start_seconds=evidence.start_seconds,
                end_seconds=evidence.end_seconds,
                modality=evidence.modality,
                content_preview=evidence.content[:280] if evidence.content is not None else None,
            )
        )
    limitations: list[str] = []
    if skipped:
        limitations.append(
            f"{skipped} evidence file(s) were invalid or unreadable and were omitted"
        )
    return evidence_projections, limitations


def _project_claims(path: Path) -> tuple[list[TraceClaim], list[str]]:
    """Project claims from the structured result without inventing review state."""
    result_path = path / "result.json"
    try:
        result = VideoAnalysisResult.model_validate_json(result_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], []
    except (OSError, UnicodeDecodeError, ValidationError, ValueError):
        return [], ["structured result was invalid or unreadable; claims were omitted"]
    return [
        TraceClaim(
            text=claim.text,
            evidence_ids=[reference.evidence_id for reference in claim.evidence],
        )
        for claim in result.claims
    ], []


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
