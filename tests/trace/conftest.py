"""Real RunBundle and TraceRecorder fixtures for truth-only trace reader tests."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from vidsnap.contracts import TerminalState, default_loop_spec
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder

PROVIDER_URL = "https://super-secret-key@trace-provider.internal/v1?api_key=leaky-query"

LANE_BASE_TYPES = (
    "run",
    "probe",
    "model.request",
    "agent.decision",
    "tool.call",
    "evidence.added",
    "verifier",
    "repair",
    "terminal",
)


@pytest.fixture
def traced_run(tmp_path: Path) -> Path:
    """A finalized RunBundle with six real, paired trace events."""
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url=PROVIDER_URL,
    )
    clock = iter((0.0, 1.0, 1.25, 1.3, 1.5, 2.0)).__next__
    recorder = TraceRecorder(bundle, clock=clock)
    run_span = recorder.start("run", phase="run")
    model_span = recorder.start("model.request", phase="agent_decision", turn=1, step=1)
    recorder.finish(
        model_span,
        status="completed",
        usage=ProviderUsage(input_tokens=7, output_tokens=3),
    )
    tool_span = recorder.start(
        "tool.call",
        phase="sample_evidence",
        turn=1,
        step=2,
        payload={"name": "sample_evidence", "api_key": "must-not-appear"},
    )
    recorder.finish(tool_span, status="completed", payload={"name": "sample_evidence"})
    recorder.finish(run_span, status="completed", phase="terminal")
    bundle.finalize(TerminalState.SUCCEEDED)
    return bundle.path


@pytest.fixture
def laned_run(tmp_path: Path) -> Path:
    """A finalized RunBundle with one paired span per registered lane base type."""
    bundle = RunBundle.create(
        tmp_path / "lanes",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    recorder = TraceRecorder(bundle, clock=itertools.count(0.0, 0.1).__next__)
    run_span = recorder.start("run", phase="run")
    for base_type in LANE_BASE_TYPES[1:]:
        span = recorder.start(base_type, phase="lane_probe")
        recorder.finish(span, status="completed")
    recorder.finish(run_span, status="completed", phase="terminal")
    bundle.finalize(TerminalState.SUCCEEDED)
    return bundle.path


@pytest.fixture
def unpaired_run(tmp_path: Path) -> Path:
    """A RunBundle whose spans cannot pair: missing, mismatched, and cross-type events."""
    bundle = RunBundle.create(
        tmp_path / "unpaired",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    bundle.append_event(
        "run",
        event_id="evt-run-start",
        event_type="run.started",
        correlation_id="corr-run",
        monotonic_offset_ms=0,
        status="started",
    )
    bundle.append_event(
        "model.request",
        event_id="evt-model-start",
        event_type="model.request.started",
        correlation_id="corr-model",
        monotonic_offset_ms=100,
        status="started",
    )
    # Same base type but a different correlation id: must not pair with the start above.
    bundle.append_event(
        "model.request",
        event_id="evt-model-done",
        event_type="model.request.completed",
        correlation_id="corr-other",
        monotonic_offset_ms=300,
        status="completed",
    )
    # Same correlation id as the model start but a different base type: must not pair.
    bundle.append_event(
        "tool.call",
        event_id="evt-tool-failed",
        event_type="tool.call.failed",
        correlation_id="corr-model",
        monotonic_offset_ms=400,
        status="failed",
    )
    bundle.finalize(TerminalState.FAILED)
    return bundle.path


@pytest.fixture
def malformed_run(traced_run: Path) -> Path:
    """A valid traced run whose ledger is corrupted with an unparseable line."""
    with (traced_run / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{this line is not json\n")
    return traced_run


@pytest.fixture
def legacy_smoke_dir(tmp_path: Path) -> Path:
    """A pre-trace benchmark result dir: no trace_schema, only outcomes.jsonl."""
    path = tmp_path / "legacy"
    path.mkdir()
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "api_version": "vidsnap.run/v1",
                "run_id": "legacy-smoke",
                "terminal_state": "SMOKE_SUCCEEDED",
            }
        )
    )
    (path / "report.json").write_text(json.dumps({"status": "SMOKE_SUCCEEDED", "case_count": 6}))
    (path / "outcomes.jsonl").write_text(
        json.dumps({"case_id": "c1", "variant": "agentic", "usage": {"model_calls": 2}}) + "\n"
    )
    return path
