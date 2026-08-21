"""Run-event ledger behavior."""

import json

import pytest

from vidsnap.contracts import ProviderUsage, default_loop_spec
from vidsnap.loop.events import RunEvent
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder


def test_event_serialization_is_timestamped_and_json_compatible() -> None:
    event = RunEvent(sequence=1, phase="probe", payload={"duration_seconds": 3.0})

    serialized = event.model_dump(mode="json")
    assert serialized["sequence"] == 1
    assert serialized["phase"] == "probe"
    assert serialized["payload"] == {"duration_seconds": 3.0}
    assert json.loads(event.to_json()) == serialized


def test_event_trace_fields_are_optional_for_legacy_readers() -> None:
    event = RunEvent(sequence=1, phase="probe")

    assert event.event_id is None
    assert event.event_type is None
    assert event.turn is None
    assert event.step is None
    assert event.parent_event_id is None
    assert event.correlation_id is None
    assert event.monotonic_offset_ms is None
    assert event.status is None
    assert event.usage is None
    assert event.duration_ms is None


def test_trace_recorder_pairs_real_start_and_completion(tmp_path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1"
    )
    recorder = TraceRecorder(bundle, clock=iter((10.0, 10.25)).__next__)
    span = recorder.start(
        "tool.call",
        phase="sample_evidence",
        turn=1,
        step=2,
        payload={"name": "sample_evidence"},
    )
    completed = recorder.finish(span, status="completed", usage=ProviderUsage(input_bytes=8))

    assert completed.correlation_id == span.correlation_id
    assert completed.duration_ms == 250
    assert completed.event_type == "tool.call.completed"
    assert completed.turn == 1
    assert completed.step == 2
    assert completed.usage is not None
    assert completed.usage.input_bytes == 8
    assert completed.usage.provider_reported is True


def test_trace_recorder_ledger_keeps_paired_start_and_failure(tmp_path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1"
    )
    recorder = TraceRecorder(bundle, clock=iter((0.0, 0.5)).__next__)
    span = recorder.start("model.request", phase="agent_decision", turn=2, step=1)
    failed = recorder.finish(span, status="failed", payload={"reason": "invalid_structure"})

    rows = [json.loads(line) for line in (bundle.path / "events.jsonl").read_text().splitlines()]
    assert [row["event_type"] for row in rows] == [
        "model.request.started",
        "model.request.failed",
    ]
    assert rows[0]["correlation_id"] == failed.correlation_id
    assert rows[0]["status"] == "started"
    assert rows[0]["duration_ms"] is None
    assert rows[1]["status"] == "failed"
    assert rows[1]["parent_event_id"] is None
    assert [row["sequence"] for row in rows] == [1, 2]


def test_trace_recorder_rejects_unknown_base_types(tmp_path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1"
    )
    recorder = TraceRecorder(bundle)

    with pytest.raises(ValueError):
        recorder.start("Tool-Call", phase="sample_evidence")


def test_trace_recorder_rejects_finishing_span_twice(tmp_path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1"
    )
    recorder = TraceRecorder(bundle, clock=iter((0.0, 0.5, 0.75)).__next__)
    span = recorder.start("tool.call", phase="sample_evidence", turn=1, step=1)
    recorder.finish(span, status="completed")

    with pytest.raises(ValueError, match="already finished"):
        recorder.finish(span, status="failed")

    rows = [json.loads(line) for line in (bundle.path / "events.jsonl").read_text().splitlines()]
    assert [row["event_type"] for row in rows] == [
        "tool.call.started",
        "tool.call.completed",
    ]
    assert [row["sequence"] for row in rows] == [1, 2]
