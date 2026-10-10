"""Local execution events (local.asr, runtime.configuration) must project into lanes."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidsnap.contracts import TerminalState, default_loop_spec
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder
from vidsnap.trace import read_trace
from vidsnap.trace.export import export_trace


@pytest.fixture
def local_execution_run(tmp_path: Path) -> Path:
    """A finalized RunBundle with paired local.asr and runtime.configuration spans.

    Offsets: run 0→900, local.asr 100→350 (completed), runtime.configuration
    400→550 (completed), local.asr 600→700 (failed).
    """
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    clock = iter((0.0, 0.1, 0.35, 0.4, 0.55, 0.6, 0.7, 0.9)).__next__
    recorder = TraceRecorder(bundle, clock=clock)
    run_span = recorder.start("run", phase="run")
    asr_span = recorder.start(
        "local.asr",
        phase="transcribe_audio",
        payload={"backend": "local_whisper", "api_key": "must-not-appear"},
    )
    recorder.finish(
        asr_span,
        status="completed",
        payload={"backend": "local_whisper", "segments": 4},
        usage=ProviderUsage(input_bytes=2048),
    )
    config_span = recorder.start(
        "runtime.configuration",
        phase="configure_runtime",
        payload={
            "backend": "local_whisper",
            "model_size": "small",
            "api_key": "must-not-appear",
        },
    )
    recorder.finish(config_span, status="completed", payload={"model_size": "small"})
    failed_span = recorder.start(
        "local.asr",
        phase="transcribe_audio",
        payload={"backend": "local_whisper"},
    )
    recorder.finish(failed_span, status="failed", payload={"error": "decoder failed"})
    recorder.finish(run_span, status="completed", phase="terminal")
    bundle.finalize(TerminalState.SUCCEEDED)
    return bundle.path


def test_local_asr_events_project_to_tools_lane(local_execution_run: Path) -> None:
    document = read_trace(local_execution_run)

    by_type = {item.event_type: item for item in document.items}
    assert "local.asr.started" in by_type
    assert "local.asr.completed" in by_type
    assert "local.asr.failed" in by_type
    for event_type in ("local.asr.started", "local.asr.completed", "local.asr.failed"):
        assert by_type[event_type].lane == "tools"
    assert by_type["local.asr.started"].duration_ms is None
    assert by_type["local.asr.completed"].duration_ms == 250
    assert by_type["local.asr.failed"].duration_ms == 100
    assert by_type["local.asr.failed"].status == "failed"


def test_local_asr_spans_do_not_count_as_model_calls(local_execution_run: Path) -> None:
    document = read_trace(local_execution_run)

    assert document.usage is not None
    assert document.usage.model_calls == 0
    assert document.usage.input_bytes == 2048


def test_runtime_configuration_projects_to_input_lane_and_redacts(
    local_execution_run: Path,
) -> None:
    document = read_trace(local_execution_run)

    by_type = {item.event_type: item for item in document.items}
    assert "runtime.configuration.started" in by_type
    assert "runtime.configuration.completed" in by_type
    started = by_type["runtime.configuration.started"]
    completed = by_type["runtime.configuration.completed"]
    assert started.lane == "input"
    assert completed.lane == "input"
    assert completed.duration_ms == 150
    assert started.payload["backend"] == "local_whisper"
    assert started.payload["model_size"] == "small"
    assert completed.payload["model_size"] == "small"
    for item in document.items:
        assert "api_key" not in item.payload


def test_no_sensitive_value_survives_projection(local_execution_run: Path) -> None:
    document = read_trace(local_execution_run)

    serialized = document.model_dump_json()
    assert "must-not-appear" not in serialized


def test_export_includes_local_execution_events(local_execution_run: Path, tmp_path: Path) -> None:
    output = export_trace(local_execution_run, tmp_path / "trace.html")

    html = output.read_text(encoding="utf-8")
    assert "local.asr.completed" in html
    assert "local.asr.failed" in html
    assert "runtime.configuration.completed" in html
    assert "must-not-appear" not in html
