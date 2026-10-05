"""A local, append-only cross-run index derived from finalized RunBundles.

The index is one JSON Lines file (``index.jsonl``) inside a runs root the user
chooses. Each finished CLI run appends one ``run`` record summarizing its
bundle; ``vidsnap runs review`` appends ``review`` records with human judgment.
Every summary is recomputable from its bundle; the index never replaces it.
Fields a bundle never recorded stay ``None``.
"""

from __future__ import annotations

import errno
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field, JsonValue, NonNegativeInt, ValidationError, model_validator
from typing_extensions import Self

from vidsnap.contracts.models import StrictModel
from vidsnap.loop.events import RunEvent
from vidsnap.trace.pricing import LoadedPriceTable, price_run

RUN_INDEX_SCHEMA = "vidsnap.run-index/v1"
INDEX_FILE_NAME = "index.jsonl"
_MIN_PREFIX_LENGTH = 8
_NO_FOLLOW = getattr(os, "O_NOFOLLOW", 0)


@dataclass(frozen=True, slots=True)
class IndexContents:
    """The parsed records of one index file plus how many lines were unusable."""

    records: list[dict[str, Any]] = field(default_factory=list)
    invalid_lines: int = 0


class RunReview(StrictModel):
    """One human review of a run's business effect; unrecorded fields stay ``None``."""

    edit_minutes: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    published: bool | None = None
    factual_errors: NonNegativeInt | None = Field(default=None, strict=True)
    images_replaced: NonNegativeInt | None = Field(default=None, strict=True)
    note: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def require_one_judgment(self) -> Self:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("a review must record at least one field")
        return self


def summarize_run(
    bundle_path: Path,
    *,
    command: str,
    price_table: LoadedPriceTable | None = None,
    outcome: str | None = None,
    outcome_reason: str | None = None,
) -> dict[str, JsonValue]:
    """Summarize one finalized RunBundle into a ``run`` index record.

    ``outcome`` and ``outcome_reason`` are what the command itself reported.
    When the command's outcome differs from the bundle's terminal state (for
    example, a verified run whose output could not be written), the record's
    ``terminal_state`` and ``failure_reason`` follow the command, and
    ``bundle_terminal_state`` keeps the bundle's own state.
    """
    bundle = bundle_path.resolve()
    manifest = _load_manifest(bundle)
    events = _load_events(bundle / "events.jsonl")

    header = _first_payload(events, "run.started")
    terminal = _terminal_run_event(events)
    terminal_payload = terminal.payload if terminal is not None else {}
    failure = terminal_payload.get("failure")
    failure = failure if isinstance(failure, dict) else {}
    provider_id, model = _provider(header, manifest)
    bundle_state = _text(manifest.get("terminal_state"))
    terminal_state = bundle_state
    failure_category = _text(failure.get("category"))
    failure_reason = _failure_reason(failure, events)
    if outcome is not None and outcome != bundle_state:
        terminal_state = outcome
        failure_reason = outcome_reason
        if failure_category is None and outcome_reason is not None:
            failure_category = "unknown"
    input_tokens, output_tokens, tokens_reported = _model_usage(events)
    budget = _last_payload(events, "budget.updated")

    return {
        "schema_version": RUN_INDEX_SCHEMA,
        "record": "run",
        "run_id": _text(manifest.get("run_id")),
        "started_at": _text(manifest.get("created_at")),
        "finalized_at": _text(manifest.get("finalized_at")),
        "indexed_at": _utc_now(),
        "command": command,
        "recipe": _text(_mapping(header.get("recipe")).get("id")),
        "policy": _text(header.get("policy")),
        "goal": _text(header.get("goal")),
        "input_sha256": _text(header.get("input_sha256")),
        "input_size_bytes": _count(header.get("input_size_bytes")),
        "input_duration_seconds": _input_duration(terminal_payload, events),
        "provider": provider_id,
        "model": model,
        "package_version": _text(manifest.get("code_version")),
        "duration_ms": _run_duration_ms(events, terminal),
        "model_calls": _count(budget.get("model_calls")),
        "tool_calls": _count(budget.get("tool_calls")),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tokens_reported": tokens_reported,
        "cost": price_run(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_reported=tokens_reported,
            price_table=price_table,
        ),
        "terminal_state": terminal_state,
        "bundle_terminal_state": bundle_state,
        "failed_gates": _failed_gates(events, manifest),
        "failure_category": failure_category,
        "http_status": _count(failure.get("http_status")),
        "failure_reason": failure_reason,
        "bundle_path": str(bundle),
    }


def review_record(run_id: str, review: RunReview) -> dict[str, JsonValue]:
    """Build one ``review`` index record for an indexed run."""
    record: dict[str, JsonValue] = {
        "schema_version": RUN_INDEX_SCHEMA,
        "record": "review",
        "run_id": run_id,
        "reviewed_at": _utc_now(),
    }
    record.update(review.model_dump(mode="json"))
    return record


def append_index_record(runs_root: Path, record: Mapping[str, JsonValue]) -> Path:
    """Append exactly one JSON line to ``<runs_root>/index.jsonl`` and return its path.

    If an earlier write left a partial last line, a newline is written first so
    the damaged line cannot swallow this record.
    """
    runs_root.mkdir(parents=True, exist_ok=True)
    index_path = runs_root / INDEX_FILE_NAME
    line = json.dumps(dict(record), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    descriptor = _open_index(index_path, os.O_RDWR | os.O_APPEND | os.O_CREAT)
    with os.fdopen(descriptor, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        prefix = b""
        if size:
            handle.seek(size - 1)
            if handle.read(1) != b"\n":
                prefix = b"\n"
        handle.write(prefix + line.encode("ascii") + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    return index_path


def read_index(runs_root: Path) -> IndexContents:
    """Read every usable index record in file order; count lines that are not.

    Undecodable bytes never stop the read: a line containing one is counted as
    unusable, like a line that is not a valid record.
    """
    index_path = runs_root / INDEX_FILE_NAME
    try:
        descriptor = _open_index(index_path, os.O_RDONLY)
    except FileNotFoundError:
        return IndexContents()
    with os.fdopen(descriptor, "rb") as handle:
        lines = handle.read().decode("utf-8", errors="replace").splitlines()
    records: list[dict[str, Any]] = []
    invalid = 0
    for line in lines:
        if not line.strip():
            continue
        if "\ufffd" in line:
            invalid += 1
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if (
            not isinstance(record, dict)
            or record.get("schema_version") != RUN_INDEX_SCHEMA
            or record.get("record") not in ("run", "review")
            or not isinstance(record.get("run_id"), str)
        ):
            invalid += 1
            continue
        records.append(record)
    return IndexContents(records=records, invalid_lines=invalid)


def latest_reviews(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Map each run id to its most recently appended review."""
    reviews: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if record.get("record") == "review":
            reviews[str(record.get("run_id"))] = record
    return reviews


def resolve_run_id(records: Sequence[Mapping[str, Any]], reference: str) -> str:
    """Resolve a run reference to an indexed run id.

    A reference is a run id, a bundle path, a bundle folder name, or a unique
    prefix of at least eight characters of a run id or bundle folder name.
    """
    run_records = [record for record in records if record.get("record") == "run"]
    run_ids = list(dict.fromkeys(str(record.get("run_id")) for record in run_records))
    if reference in run_ids:
        return reference
    folders: dict[str, str] = {}
    for record in run_records:
        bundle_path = record.get("bundle_path")
        if isinstance(bundle_path, str) and bundle_path:
            folders[Path(bundle_path).name] = str(record.get("run_id"))
    candidate = Path(reference).expanduser()
    if candidate.is_dir():
        resolved = str(candidate.resolve())
        for record in run_records:
            if record.get("bundle_path") == resolved:
                return str(record.get("run_id"))
    if reference in folders:
        return folders[reference]
    if len(reference) < _MIN_PREFIX_LENGTH:
        raise LookupError(
            f"run reference {reference!r} must be at least {_MIN_PREFIX_LENGTH} characters"
        )
    matches = {run_id for run_id in run_ids if run_id.startswith(reference)}
    matches.update(run_id for name, run_id in folders.items() if name.startswith(reference))
    if len(matches) > 1:
        raise LookupError(f"{reference!r} is ambiguous; use more of the run id")
    if not matches:
        raise LookupError(f"no indexed run matches {reference!r}")
    return matches.pop()


def _open_index(index_path: Path, flags: int) -> int:
    """Open the index without following a symbolic link; new files are owner-only."""
    if not _NO_FOLLOW and index_path.is_symlink():
        raise OSError(errno.ELOOP, "run index must not be a symbolic link", str(index_path))
    return os.open(index_path, flags | _NO_FOLLOW, 0o600)


_TABLE_COLUMNS = (
    "RUN",
    "STARTED",
    "COMMAND",
    "STATE",
    "DURATION",
    "INPUT",
    "TOKENS IN/OUT",
    "COST",
    "FAILED GATES",
    "FAILURE",
    "REVIEW",
    "BUNDLE",
)


def render_run_table(records: Sequence[Mapping[str, Any]]) -> str:
    """Render indexed runs, oldest first, with each run's latest review, as plain text."""
    reviews = latest_reviews(records)
    rows = [list(_TABLE_COLUMNS)]
    for record in records:
        if record.get("record") != "run":
            continue
        rows.append(_table_row(record, reviews.get(str(record.get("run_id")))))
    widths = [max(len(row[column]) for row in rows) for column in range(len(_TABLE_COLUMNS))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows
    )


def _table_row(record: Mapping[str, Any], review: Mapping[str, Any] | None) -> list[str]:
    started = _text(record.get("started_at"))
    duration = _count(record.get("duration_ms"))
    sha = _text(record.get("input_sha256"))
    gates = record.get("failed_gates")
    tokens = f"{_count(record.get('input_tokens')) or 0}/{_count(record.get('output_tokens')) or 0}"
    if record.get("tokens_reported") is not True:
        tokens += "?"
    return [
        str(record.get("run_id"))[:8],
        started[:19].replace("T", " ") if started is not None else "-",
        _text(record.get("command")) or "-",
        _text(record.get("terminal_state")) or "-",
        f"{duration / 1000:.1f}s" if duration is not None else "-",
        sha[:12] if sha is not None else "-",
        tokens,
        _cost_cell(record.get("cost")),
        (",".join(str(gate) for gate in gates) or "none") if isinstance(gates, list) else "-",
        _text(record.get("failure_category")) or "-",
        _review_cell(review),
        _text(record.get("bundle_path")) or "-",
    ]


def _cost_cell(cost: object) -> str:
    if not isinstance(cost, dict):
        return "-"
    amount = cost.get("amount")
    if isinstance(amount, (int, float)) and not isinstance(amount, bool):
        return f"{amount:.4f} {cost.get('currency', '')}".rstrip()
    return "unknown"


def _review_cell(review: Mapping[str, Any] | None) -> str:
    if review is None:
        return "-"
    parts: list[str] = []
    published = review.get("published")
    if isinstance(published, bool):
        parts.append("published" if published else "not published")
    minutes = review.get("edit_minutes")
    if isinstance(minutes, (int, float)) and not isinstance(minutes, bool):
        parts.append(f"{minutes:g} min edit")
    errors = _count(review.get("factual_errors"))
    if errors is not None:
        parts.append(f"{errors} errors")
    images = _count(review.get("images_replaced"))
    if images is not None:
        parts.append(f"{images} images replaced")
    if _text(review.get("note")) is not None:
        parts.append("note")
    return ", ".join(parts) or "-"


def _load_manifest(bundle: Path) -> dict[str, Any]:
    try:
        loaded = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"not a RunBundle (manifest missing or unreadable): {bundle}") from error
    if not isinstance(loaded, dict):
        raise ValueError(f"not a RunBundle (manifest is not an object): {bundle}")
    return loaded


def _load_events(ledger: Path) -> list[RunEvent]:
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("RunBundle event ledger is unreadable") from error
    events: list[RunEvent] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(RunEvent.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            raise ValueError(f"invalid RunBundle ledger entry at line {number}") from error
    return events


def _first_payload(events: Sequence[RunEvent], event_type: str) -> dict[str, Any]:
    for event in events:
        if event.event_type == event_type:
            return dict(event.payload)
    return {}


def _last_payload(events: Sequence[RunEvent], event_type: str) -> dict[str, Any]:
    for event in reversed(events):
        if event.event_type == event_type:
            return dict(event.payload)
    return {}


def _terminal_run_event(events: Sequence[RunEvent]) -> RunEvent | None:
    for event in reversed(events):
        event_type = event.event_type or ""
        if event_type.startswith("run.") and event.status not in (None, "started"):
            return event
    return None


def _run_duration_ms(events: Sequence[RunEvent], terminal: RunEvent | None) -> int | None:
    if terminal is None:
        return None
    if terminal.duration_ms is not None:
        return terminal.duration_ms
    for event in events:
        if (
            event.event_type == "run.started"
            and event.correlation_id == terminal.correlation_id
            and event.monotonic_offset_ms is not None
            and terminal.monotonic_offset_ms is not None
        ):
            duration = terminal.monotonic_offset_ms - event.monotonic_offset_ms
            return duration if duration >= 0 else None
    return None


def _input_duration(
    terminal_payload: Mapping[str, Any], events: Sequence[RunEvent]
) -> float | None:
    recorded = _seconds(terminal_payload.get("input_duration_seconds"))
    if recorded is not None:
        return recorded
    return _seconds(_last_payload(events, "probe.completed").get("duration_seconds"))


def _provider(
    header: Mapping[str, Any], manifest: Mapping[str, Any]
) -> tuple[str | None, str | None]:
    for source in (_mapping(header.get("provider")), _mapping(manifest.get("provider"))):
        provider_id, model = _text(source.get("id")), _text(source.get("model"))
        if provider_id is not None or model is not None:
            return provider_id, model
    return None, None


def _model_usage(events: Sequence[RunEvent]) -> tuple[int, int, bool]:
    """Sum model-request token usage; ``reported`` is False if any attempt went unreported."""
    input_tokens = 0
    output_tokens = 0
    reported = True
    for event in events:
        event_type = event.event_type or ""
        is_model_request = event_type in ("model.request.completed", "model.request.failed")
        is_model_lane_usage = event_type.startswith("agent.decision") and event.usage is not None
        if not (is_model_request or is_model_lane_usage):
            continue
        if event.usage is None:
            reported = False
            continue
        input_tokens += event.usage.input_tokens
        output_tokens += event.usage.output_tokens
        reported = reported and event.usage.provider_reported
    return input_tokens, output_tokens, reported


def _failed_gates(
    events: Sequence[RunEvent], manifest: Mapping[str, Any]
) -> list[JsonValue] | None:
    for event in reversed(events):
        if event.event_type == "verifier.completed":
            gates = event.payload.get("failed_gates")
            if isinstance(gates, list):
                return [gate for gate in gates if isinstance(gate, str)]
    gates = _mapping(manifest.get("verification")).get("failed_gates")
    if isinstance(gates, list):
        return [gate for gate in gates if isinstance(gate, str)]
    return None


def _failure_reason(failure: Mapping[str, Any], events: Sequence[RunEvent]) -> str | None:
    reason = _text(failure.get("reason"))
    if reason is not None:
        return reason
    for event in reversed(events):
        if event.event_type == "phase.completed" and event.phase == "terminal":
            recorded = _text(event.payload.get("reason"))
            return None if recorded in (None, "completed") else recorded
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _count(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _seconds(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
