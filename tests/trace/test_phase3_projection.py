"""RED tests for the Phase 3 truth-only projection of overview, budget, evidence and claims."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vidsnap.contracts import (
    Claim,
    Evidence,
    EvidenceReference,
    TerminalState,
    VideoAnalysisResult,
    default_loop_spec,
)
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder
from vidsnap.trace import read_trace
from vidsnap.trace.export import export_trace

GOAL = "Summarize the recorded talk"
INPUT_SHA256 = "a" * 64
PROVIDER_URL = "https://super-secret-key@trace-provider.internal/v1?api_key=leaky-query"
SECRET_HOST = "trace-provider.internal"
SECRET_QUERY = "leaky-query"
TERMINAL_STATES = (
    TerminalState.SUCCEEDED,
    TerminalState.PARTIAL,
    TerminalState.FAILED,
    TerminalState.EXHAUSTED,
    TerminalState.BLOCKED,
)


def build_finalized_bundle(path: Path, terminal_state: TerminalState) -> Path:
    """Record a rich, valid RunBundle: evidence, result, run span and budget snapshot."""
    bundle = RunBundle.create(path, loop_spec=default_loop_spec(), provider_url=PROVIDER_URL)
    evidence = Evidence(
        id="transcript-001",
        start_seconds=0.0,
        end_seconds=12.5,
        modality="transcript",
        content="e" * 320,
    )
    claim = Claim(
        text="Recorded claim",
        evidence=[EvidenceReference(evidence_id="transcript-001")],
    )
    result = VideoAnalysisResult(summary="Recorded summary", claims=[claim])
    bundle.write_evidence(evidence)
    bundle.write_result(result)
    recorder = TraceRecorder(bundle, clock=iter((0.0, 1.25)).__next__)
    run_span = recorder.start(
        "run",
        phase="run",
        payload={"goal": GOAL, "input_sha256": INPUT_SHA256},
    )
    bundle.append_event(
        "budget",
        {"iterations": 2, "tool_calls": 1, "model_calls": 1, "evidence_frames": 1},
        event_type="budget.updated",
        monotonic_offset_ms=1250,
    )
    recorder.finish(run_span, status="completed", phase="terminal")
    bundle.finalize(terminal_state)
    return bundle.path


SENSITIVE_KEY_NAMES = (
    "authorization",
    "api_key",
    "access_token",
    "pat_token",
    "x-secret-header",
    "ARBITRARY_ENV_VAR",
    "chain_of_thought",
    "internal_reasoning",
)

SENSITIVE_VALUES = (
    "sentinel-bearer-auth-9d2f1c",
    "sentinel-api-key-4b7e2a",
    "sentinel-pat-token-1c8a7f",
    "sentinel-secret-header-5e2b3d",
    "sentinel-path-env-6f3d0b:/usr/local/bin",
    "/Users/sentinel-home-2a9e4c",
    "sentinel-arbitrary-env-8c4f1e",
    "sentinel-chain-of-thought-a1b2c3",
    "sentinel-reasoning-c3d4e5",
    "sentinel-internal-reasoning-e5f6a7",
    "/Users/sentinel-user-9e7f8b/secret/media.mp4",
    "https://sentinel-provider-host-3f5a6c.internal/v1?api_key=sentinel-query-7d6c0e",
)

ADVERSARIAL_PAYLOAD: dict[str, object] = {
    "authorization": "Bearer sentinel-bearer-auth-9d2f1c",
    "api_key": "sentinel-api-key-4b7e2a",
    "access_token": "sentinel-pat-token-1c8a7f",
    "pat_token": "sentinel-pat-token-1c8a7f",
    "headers": {
        "x-secret-header": "sentinel-secret-header-5e2b3d",
        "authorization": "Bearer sentinel-bearer-auth-9d2f1c",
    },
    "env": {
        "PATH": "sentinel-path-env-6f3d0b:/usr/local/bin",
        "HOME": "/Users/sentinel-home-2a9e4c",
        "ARBITRARY_ENV_VAR": "sentinel-arbitrary-env-8c4f1e",
    },
    "chain_of_thought": "sentinel-chain-of-thought-a1b2c3",
    "reasoning": "sentinel-reasoning-c3d4e5",
    "internal_reasoning": "sentinel-internal-reasoning-e5f6a7",
    "artifact_path": "/Users/sentinel-user-9e7f8b/secret/media.mp4",
    "base_url": "https://sentinel-provider-host-3f5a6c.internal/v1?api_key=sentinel-query-7d6c0e",
}


def inject_raw_adversarial_event(run: Path) -> None:
    """Append a sensitive-laden event line directly, bypassing write-time redaction."""
    raw_line = json.dumps(
        {
            "sequence": 99,
            "phase": "adversarial",
            "event_type": "model.request",
            "status": "completed",
            "monotonic_offset_ms": 1500,
            "payload": ADVERSARIAL_PAYLOAD,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    with (run / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(raw_line)
        handle.write("\n")


def test_reader_and_export_boundary_strips_sensitive_fields_from_raw_ledger(
    tmp_path: Path,
) -> None:
    run = build_finalized_bundle(tmp_path / "run", TerminalState.SUCCEEDED)
    inject_raw_adversarial_event(run)

    ledger = (run / "events.jsonl").read_text(encoding="utf-8")
    for value in SENSITIVE_VALUES:
        assert value in ledger, "precondition: raw ledger must still contain the sentinel"

    document = read_trace(run)
    doc_json = document.model_dump_json()
    for marker in SENSITIVE_VALUES + SENSITIVE_KEY_NAMES:
        assert marker not in doc_json, f"trace document leaked sensitive marker {marker!r}"

    html = export_trace(run, tmp_path / "adversarial.html").read_text(encoding="utf-8")
    for marker in SENSITIVE_VALUES + SENSITIVE_KEY_NAMES:
        assert marker not in html, f"exported HTML leaked sensitive marker {marker!r}"

    assert document.overview.goal == GOAL
    assert document.evidence[0].content_preview is not None
    assert set(document.evidence[0].content_preview) == {"e"}
    assert document.claims[0].text == "Recorded claim"


def test_projection_exposes_exact_recorded_overview_budget_evidence_and_claims(
    tmp_path: Path,
) -> None:
    run = build_finalized_bundle(tmp_path / "run", TerminalState.SUCCEEDED)
    document = read_trace(run)

    assert document.overview.goal == GOAL
    assert document.overview.input_sha256 == INPUT_SHA256
    assert document.overview.status == TerminalState.SUCCEEDED.value
    assert document.overview.duration_ms == 1250
    assert document.overview.provider == "configured (identity redacted)"
    assert document.overview.recipe == "grounded-video-understanding"

    assert document.budget.model_calls.used == 1
    assert document.budget.model_calls.limit == 12
    assert document.budget.evidence_frames.used == 1
    assert document.budget.evidence_frames.limit == 96
    assert document.budget.iterations.used == 2
    assert document.budget.iterations.limit == 3
    assert document.budget.runtime_ms.used == 1250
    assert document.budget.runtime_ms.limit == 900000

    evidence = document.evidence[0]
    assert evidence.evidence_id == "transcript-001"
    assert evidence.start_seconds == 0.0
    assert evidence.end_seconds == 12.5
    assert evidence.modality == "transcript"
    preview = evidence.content_preview
    assert preview
    assert len(preview) <= 280
    assert set(preview) == {"e"}
    assert evidence.source is None
    assert evidence.speaker is None
    assert evidence.frame is None
    assert evidence.confidence is None

    claim = document.claims[0]
    assert claim.text == "Recorded claim"
    assert claim.evidence_ids == ["transcript-001"]
    assert claim.verification_result is None
    assert claim.editorial_status is None


@pytest.mark.parametrize("state", TERMINAL_STATES)
def test_export_is_offline_and_carries_the_exact_terminal_state(
    tmp_path: Path,
    state: TerminalState,
) -> None:
    run = build_finalized_bundle(tmp_path / state.value.lower(), state)
    output = export_trace(run, tmp_path / f"{state.value.lower()}.html")
    html = output.read_text(encoding="utf-8")

    assert state.value in html
    for forbidden in ("https://", "fetch(", "WebSocket", SECRET_HOST, SECRET_QUERY):
        assert forbidden not in html, f"offline export must not contain {forbidden!r}"


def test_exported_html_renders_the_phase3_section_labels(tmp_path: Path) -> None:
    run = build_finalized_bundle(tmp_path / "run", TerminalState.SUCCEEDED)
    output = export_trace(run, tmp_path / "trace.html")
    html = output.read_text(encoding="utf-8")

    for label in ("Run Overview", "Budget", "Agent Timeline", "Evidence", "Claims", "Privacy"):
        assert label in html
