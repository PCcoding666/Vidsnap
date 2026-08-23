"""Auditable filesystem RunBundle behavior."""

import json

from vidsnap.contracts import (
    Claim,
    Evidence,
    EvidenceReference,
    TerminalState,
    VideoAnalysisResult,
    default_loop_spec,
)
from vidsnap.loop.run_bundle import RunBundle, temporary_run_bundle


def test_run_bundle_writes_required_files_with_redacted_provider_and_hashes(tmp_path) -> None:
    run_path = tmp_path / "run"
    bundle = RunBundle.create(
        run_path,
        loop_spec=default_loop_spec(),
        provider_url="https://secret-token@host/v1?api_key=another-secret",
    )
    bundle.append_event("probe", {"duration_seconds": 3.0})
    bundle.write_evidence(Evidence(id="ev-1", start_seconds=0, end_seconds=1, modality="frame"))
    bundle.write_result(
        VideoAnalysisResult(
            summary="A grounded summary.",
            claims=[
                Claim(
                    text="A visible event occurs.", evidence=[EvidenceReference(evidence_id="ev-1")]
                )
            ],
        )
    )
    bundle.finalize(TerminalState.SUCCEEDED)

    manifest = json.loads((run_path / "manifest.json").read_text())
    assert (run_path / "events.jsonl").exists()
    assert (run_path / "evidence" / "ev-1.json").exists()
    assert (run_path / "result.json").exists()
    assert (run_path / "artifacts").is_dir()
    assert manifest["provider"]["base_url"] == "https://host/v1"
    assert manifest["terminal_state"] == "SUCCEEDED"
    assert len(manifest["files"]["result.json"]["sha256"]) == 64
    assert "secret" not in "\n".join(
        path.read_text() for path in run_path.rglob("*") if path.is_file()
    )


def test_temporary_run_bundle_is_cleaned_up_at_context_exit(tmp_path) -> None:
    with temporary_run_bundle(
        parent=tmp_path,
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    ) as bundle:
        run_path = bundle.path
        assert run_path.exists()

    assert not run_path.exists()


def test_run_manifest_declares_trace_schema_without_changing_run_version(tmp_path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1"
    )
    manifest = json.loads((bundle.path / "manifest.json").read_text())
    assert manifest["api_version"] == "vidsnap.run/v1"
    assert manifest["trace_schema"] == "vidsnap.trace/v1"


def test_append_event_accepts_trace_fields_and_still_redacts(tmp_path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run", loop_spec=default_loop_spec(), provider_url="https://host/v1"
    )

    event = bundle.append_event(
        "tool.call",
        {"name": "sample_evidence", "api_key": "must-not-appear"},
        event_id="evt-1",
        event_type="tool.call.started",
        turn=1,
        step=2,
        correlation_id="corr-1",
        monotonic_offset_ms=120,
        status="started",
    )

    assert event.event_type == "tool.call.started"
    assert event.correlation_id == "corr-1"
    assert event.status == "started"
    assert event.payload == {
        "name": "sample_evidence",
        "api_key": "***REDACTED***",
    }
    legacy_event = bundle.append_event("probe", {"duration_seconds": 3.0})
    assert legacy_event.event_type is None
    assert legacy_event.status is None


def test_run_bundle_preserves_numeric_usage_counts_but_redacts_credentials(tmp_path) -> None:
    """Removing usage counters or exposing a credential-like token must fail this test."""
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )

    event = bundle.append_event(
        "usage",
        {"input_tokens": 11, "output_tokens": 3, "api_token": "must-not-appear"},
    )

    assert event.payload == {
        "input_tokens": 11,
        "output_tokens": 3,
        "api_token": "***REDACTED***",
    }
