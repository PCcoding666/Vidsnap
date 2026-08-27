"""Real RunBundle and TraceRecorder fixtures for truth-only trace reader tests."""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from vidsnap.contracts import TerminalState, default_loop_spec
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.models import Evidence
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
def timed_run(tmp_path: Path) -> Path:
    """A finalized RunBundle whose recorded run duration is exactly 450 ms.

    Offsets: run 0→450, model.request 120→200, tool.call 310→400.
    """
    bundle = RunBundle.create(
        tmp_path / "timed",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    clock = iter((0.0, 0.12, 0.2, 0.31, 0.4, 0.45)).__next__
    recorder = TraceRecorder(bundle, clock=clock)
    run_span = recorder.start("run", phase="run")
    model_span = recorder.start("model.request", phase="agent_decision", turn=1, step=1)
    recorder.finish(model_span, status="completed")
    tool_span = recorder.start("tool.call", phase="sample_evidence", turn=1, step=2)
    recorder.finish(tool_span, status="completed")
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


@pytest.fixture
def escaping_run(tmp_path: Path) -> Path:
    """A finalized RunBundle whose recorded payload contains raw HTML markup."""
    bundle = RunBundle.create(
        tmp_path / "escaping",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    recorder = TraceRecorder(bundle, clock=iter((0.0, 0.5, 1.0)).__next__)
    run_span = recorder.start(
        "run",
        phase="run",
        payload={"objective": 'answer </script><script>alert("x")</script>'},
    )
    recorder.finish(run_span, status="completed", phase="terminal")
    bundle.finalize(TerminalState.SUCCEEDED)
    return bundle.path


@pytest.fixture
def run_with_evidence(traced_run: Path) -> Path:
    """A traced run that also carries real evidence and artifact files on disk."""
    (traced_run / "evidence" / "frame-001.json").write_text(
        json.dumps(
            Evidence(
                id="frame-001",
                start_seconds=0.0,
                end_seconds=1.0,
                modality="frame",
                content="PREVIEW_MARKER_7a2f sampled opening frame description",
            ).model_dump(mode="json")
        )
    )
    artifact_dir = traced_run / "artifacts" / "turn-1"
    artifact_dir.mkdir()
    (artifact_dir / "frame-001.jpg").write_bytes(b"\xff\xd8ARTIFACT_BYTES_77e1")
    return traced_run


def _record_variant(path: Path, steps: Callable[[TraceRecorder], None]) -> None:
    bundle = RunBundle.create(
        path,
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    recorder = TraceRecorder(bundle, clock=itertools.count(0.0, 0.05).__next__)
    run_span = recorder.start("run", phase="run")
    steps(recorder)
    recorder.finish(run_span, status="completed", phase="terminal")
    bundle.finalize(TerminalState.SUCCEEDED)


@pytest.fixture
def variant_case_dir(tmp_path: Path) -> Path:
    """A benchmark case directory with Direct, Fixed and Agentic variant runs."""
    case_dir = tmp_path / "case"

    def direct_steps(recorder: TraceRecorder) -> None:
        probe = recorder.start("probe", phase="probe_media")
        recorder.finish(probe, status="completed")
        evidence = recorder.start(
            "evidence.added",
            phase="prepare_direct_baseline",
            payload={"id": "frame-001"},
        )
        recorder.finish(evidence, status="completed", payload={"id": "frame-001"})
        model = recorder.start("model.request", phase="synthesize_result")
        recorder.finish(model, status="completed")

    def fixed_steps(recorder: TraceRecorder) -> None:
        probe = recorder.start("probe", phase="probe_media")
        recorder.finish(probe, status="completed")
        first = recorder.start(
            "tool.call", phase="transcribe_audio", payload={"name": "transcribe_audio"}
        )
        recorder.finish(first, status="completed", payload={"name": "transcribe_audio"})
        second = recorder.start(
            "tool.call", phase="sample_evidence", payload={"name": "sample_evidence"}
        )
        recorder.finish(second, status="completed", payload={"name": "sample_evidence"})
        model = recorder.start("model.request", phase="synthesize_result")
        recorder.finish(model, status="completed")

    def agentic_steps(recorder: TraceRecorder) -> None:
        probe = recorder.start("probe", phase="probe_media")
        recorder.finish(probe, status="completed")
        decision = recorder.start("model.request", phase="agent_decision", turn=1, step=1)
        recorder.finish(decision, status="completed")
        tool = recorder.start(
            "tool.call",
            phase="sample_evidence",
            turn=1,
            step=2,
            payload={"name": "sample_evidence"},
        )
        recorder.finish(tool, status="completed", payload={"name": "sample_evidence"})
        final = recorder.start("model.request", phase="agent_decision", turn=2, step=3)
        recorder.finish(final, status="completed")

    _record_variant(case_dir / "direct" / "run", direct_steps)
    _record_variant(case_dir / "fixed" / "run", fixed_steps)
    _record_variant(case_dir / "agentic" / "run", agentic_steps)
    return case_dir
