"""RED tests for the truth-only RunBundle trace reader (vidsnap.trace)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from vidsnap.trace import TraceDocument, TraceLane, read_trace

EXPECTED_LANES: dict[str, TraceLane] = {
    "run.started": "input",
    "run.completed": "input",
    "probe.started": "input",
    "probe.completed": "input",
    "model.request.started": "model",
    "model.request.completed": "model",
    "agent.decision.started": "model",
    "agent.decision.completed": "model",
    "tool.call.started": "tools",
    "tool.call.completed": "tools",
    "evidence.added.started": "tools",
    "evidence.added.completed": "tools",
    "verifier.started": "verifier",
    "verifier.completed": "verifier",
    "repair.started": "verifier",
    "repair.completed": "verifier",
    "terminal.started": "verifier",
    "terminal.completed": "verifier",
}


def _item(trace: TraceDocument, event_type: str) -> Any:
    matches = [item for item in trace.items if item.event_type == event_type]
    assert len(matches) == 1, f"expected exactly one {event_type} item, got {len(matches)}"
    return matches[0]


def test_reader_projects_only_recorded_events_in_chronological_order(
    traced_run: Path,
) -> None:
    trace = read_trace(traced_run)

    assert [item.event_type for item in trace.items] == [
        "run.started",
        "model.request.started",
        "model.request.completed",
        "tool.call.started",
        "tool.call.completed",
        "run.completed",
    ]
    offsets = [item.offset_ms for item in trace.items]
    assert offsets == sorted(offsets) == [0, 1000, 1250, 1300, 1500, 2000]
    assert trace.summary_only is False


def test_paired_spans_carry_measured_durations(traced_run: Path) -> None:
    trace = read_trace(traced_run)

    assert trace.duration_ms == 2_000
    assert _item(trace, "run.completed").duration_ms == 2_000
    assert _item(trace, "model.request.completed").duration_ms == 250
    assert _item(trace, "tool.call.completed").duration_ms == 200
    assert _item(trace, "run.started").duration_ms is None
    assert _item(trace, "model.request.started").duration_ms is None
    assert _item(trace, "tool.call.started").duration_ms is None


def test_lanes_follow_the_registered_base_type_mapping(laned_run: Path) -> None:
    trace = read_trace(laned_run)

    assert {item.event_type: item.lane for item in trace.items} == EXPECTED_LANES


def test_pairing_requires_matching_correlation_id_and_base_type(
    unpaired_run: Path,
) -> None:
    trace = read_trace(unpaired_run)

    # The completed model event carries a different correlation id: no pair.
    assert _item(trace, "model.request.started").duration_ms is None
    assert _item(trace, "model.request.completed").duration_ms is None
    # The failed tool event reuses the model correlation id but not its base type.
    assert _item(trace, "tool.call.failed").duration_ms is None


def test_overall_duration_requires_a_paired_run_span(unpaired_run: Path) -> None:
    trace = read_trace(unpaired_run)

    assert trace.summary_only is False
    assert trace.duration_ms is None


def test_unpaired_items_preserve_recorded_status_without_duration(
    unpaired_run: Path,
) -> None:
    trace = read_trace(unpaired_run)

    assert _item(trace, "model.request.completed").status == "completed"
    assert _item(trace, "tool.call.failed").status == "failed"
    assert _item(trace, "run.started").status == "started"


def test_payload_and_usage_stay_typed_and_redacted(traced_run: Path) -> None:
    trace = read_trace(traced_run)

    tool_started = _item(trace, "tool.call.started")
    assert tool_started.payload == {
        "name": "sample_evidence",
        "api_key": "***REDACTED***",
    }
    model_completed = _item(trace, "model.request.completed")
    assert model_completed.usage is not None
    assert model_completed.usage.input_tokens == 7
    assert model_completed.usage.output_tokens == 3
    assert "must-not-appear" not in trace.model_dump_json()


def test_provider_url_never_appears_in_the_trace_document(traced_run: Path) -> None:
    trace = read_trace(traced_run)

    serialized = trace.model_dump_json()
    assert "trace-provider.internal" not in serialized
    assert "super-secret-key" not in serialized
    assert "leaky-query" not in serialized


def test_malformed_events_jsonl_fails_safely(malformed_run: Path) -> None:
    with pytest.raises(ValueError):
        read_trace(malformed_run)


def test_legacy_outcome_is_summary_only_and_has_no_invented_duration(
    legacy_smoke_dir: Path,
) -> None:
    trace = read_trace(legacy_smoke_dir)

    assert trace.summary_only is True
    assert trace.duration_ms is None
    assert all(item.duration_ms is None for item in trace.items)
    assert "step-level events were not recorded" in trace.limitations


def test_legacy_outcome_keeps_only_terminal_and_outcome_usage_metadata(
    legacy_smoke_dir: Path,
) -> None:
    trace = read_trace(legacy_smoke_dir)

    assert trace.terminal_state == "SMOKE_SUCCEEDED"
    assert trace.usage is not None
    assert trace.usage.model_calls == 2
    # No step rows may be invented from the final outcome.
    assert not any(
        item.event_type.startswith(("model.", "tool.", "run.", "probe.")) for item in trace.items
    )
