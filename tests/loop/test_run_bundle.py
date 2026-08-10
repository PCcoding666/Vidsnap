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
