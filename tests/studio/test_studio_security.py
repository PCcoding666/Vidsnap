"""Security-stripping tests: the projection never leaks secrets or identity."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from vidsnap.studio.export import export_studio
from vidsnap.studio.project import StudioDocument, project_studio

HOSTILE_STRINGS = (
    "must-not-appear",
    "super-secret-key",
    "leak-key",
    "leaky-query",
    "studio-provider.internal",
    "Bearer zqxwv-credential",
    "zqxwv-credential",
    "chain-of-thought leak marker",
    "internal reasoning leak marker",
    "qwen-secret-model-name",
    "https://provider-base.internal/v1",
)


@pytest.fixture
def hostile_root(tmp_path: Path, build_bundle) -> Path:
    """A manifest root whose ledger carries secrets, CoT, and absolute paths."""
    root = tmp_path / "hostile"
    build_bundle(
        root,
        "runs/v0/case-01/t1",
        run_payload={
            "goal": "summarize /Users/leaky/videos/private.mp4",
            "api_key": "must-not-appear",
            "authorization": "Bearer zqxwv-credential",
            "chain_of_thought": "chain-of-thought leak marker",
            "internal_reasoning": "internal reasoning leak marker",
            "scratchpad": "scratchpad leak marker",
            "provider_response": {
                "model": "qwen-secret-model-name",
                "base_url": "https://provider-base.internal/v1",
                "body": "raw provider body marker",
            },
        },
    )
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "api_version": "vidsnap.studio/v1",
        "title": "Notes about /Users/leaky/workspace recordings",
        "iteration": {
            "agent_id": "video-summarizer",
            "versions": [
                {
                    "version": "v0",
                    "summary": "baseline prompt",
                    "cases": [
                        {
                            "case_id": "case-01",
                            "trials": [{"trial_id": "t1", "run": "runs/v0/case-01/t1"}],
                        }
                    ],
                }
            ],
        },
    }
    (root / "studio.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


@pytest.fixture
def hostile_serialized(hostile_root: Path) -> str:
    return project_studio(hostile_root / "studio.json").model_dump_json()


@pytest.mark.parametrize("hostile", HOSTILE_STRINGS)
def test_serialized_projection_excludes_hostile_values(
    hostile_serialized: str, hostile: str
) -> None:
    assert hostile not in hostile_serialized


def test_provider_url_credentials_never_leak(hostile_serialized: str, provider_url: str) -> None:
    assert provider_url not in hostile_serialized
    assert "configured (identity redacted)" in hostile_serialized


def test_absolute_local_paths_are_stripped_from_manifest_and_ledger_text(
    hostile_serialized: str,
) -> None:
    assert "/Users/" not in hostile_serialized
    assert "/home/" not in hostile_serialized
    assert "private.mp4" not in hostile_serialized
    assert "***REDACTED***" in hostile_serialized


def test_run_references_stay_manifest_relative(hostile_root: Path) -> None:
    document = project_studio(hostile_root / "studio.json")
    trial = document.iteration.eval_cases[0].entries[0].trials[0]
    assert trial.run == "runs/v0/case-01/t1"
    assert str(hostile_root) not in trial.run
    assert not trial.run.startswith("/")


def test_answer_panel_only_carries_recorded_claims(hostile_root: Path) -> None:
    document = project_studio(hostile_root / "studio.json")
    trial = document.iteration.eval_cases[0].entries[0].trials[0]
    assert trial.answer.claims == ()
    assert trial.answer.provenance == "not_recorded"


def test_in_memory_projection_matches_serialized_form(hostile_root: Path) -> None:
    document = project_studio(hostile_root / "studio.json")
    dumped = json.loads(document.model_dump_json())
    assert dumped == document.model_dump(mode="json")


ABSOLUTE_PATH_PROBES = (
    "/private/var/folders/demo.txt",
    "/var/folders/ab/run.log",
    "/tmp/vidsnap/demo.mp4",
    "/Volumes/Backup/media/demo.mp4",
    "C:\\Users\\demo\\videos\\demo.mp4",
)


@pytest.mark.parametrize("probe", ABSOLUTE_PATH_PROBES)
def test_absolute_path_shapes_are_replaced_with_the_redaction_marker(probe: str) -> None:
    serialized = StudioDocument(title=f"notes {probe}").model_dump_json()
    assert probe not in serialized
    assert "***REDACTED***" in serialized


@pytest.mark.parametrize("probe", ABSOLUTE_PATH_PROBES)
def test_ledger_and_manifest_absolute_paths_never_leak(
    tmp_path: Path, build_bundle, probe: str
) -> None:
    root = tmp_path / "paths"
    build_bundle(root, "runs/v0/case-01/t1", run_payload={"goal": f"inspect {probe} now"})
    payload = {
        "api_version": "vidsnap.studio/v1",
        "title": f"notes about {probe} recordings",
        "iteration": {
            "agent_id": "video-summarizer",
            "versions": [
                {
                    "version": "v0",
                    "summary": f"baseline {probe}",
                    "cases": [
                        {
                            "case_id": "case-01",
                            "trials": [{"trial_id": "t1", "run": "runs/v0/case-01/t1"}],
                        }
                    ],
                }
            ],
        },
    }
    manifest_path = root / "studio.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    document = project_studio(manifest_path)
    serialized = document.model_dump_json()
    assert probe not in serialized
    assert "***REDACTED***" in serialized

    output = tmp_path / "paths.html"
    export_studio(manifest_path, output)
    html = output.read_text(encoding="utf-8")
    assert probe not in html
    assert "***REDACTED***" in html


def test_manifest_relative_run_refs_survive_path_redaction(hostile_root: Path) -> None:
    serialized = project_studio(hostile_root / "studio.json").model_dump_json()
    assert "runs/v0/case-01/t1" in serialized
    assert "***REDACTED***/v0" not in serialized


def _write_single_trial_manifest(root: Path) -> Path:
    payload = {
        "api_version": "vidsnap.studio/v1",
        "iteration": {
            "agent_id": "escape-probe",
            "versions": [
                {
                    "version": "v0",
                    "summary": "escape probe",
                    "cases": [
                        {
                            "case_id": "case-01",
                            "trials": [{"trial_id": "t1", "run": "runs/v0/case-01/t1"}],
                        }
                    ],
                }
            ],
        },
    }
    path = root / "studio.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("member", ("events.jsonl", "outcomes.jsonl", "result.json"))
def test_bundle_member_symlink_escape_is_refused_before_projection(
    tmp_path: Path, build_bundle, member: str
) -> None:
    root = tmp_path / "escape"
    build_bundle(root, "runs/v0/case-01/t1")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / member
    outside_file.write_text("EXTERNAL_ESCAPE_MARKER", encoding="utf-8")
    target = root / "runs/v0/case-01/t1" / member
    target.unlink(missing_ok=True)
    os.symlink(outside_file, target)
    manifest_path = _write_single_trial_manifest(root)

    with pytest.raises(ValueError) as excinfo:
        project_studio(manifest_path)

    message = str(excinfo.value)
    assert str(outside_file) not in message
    assert str(root) not in message
    assert "EXTERNAL_ESCAPE_MARKER" not in message


def test_evidence_directory_symlink_escape_is_refused(tmp_path: Path, build_bundle) -> None:
    root = tmp_path / "escape-evidence-dir"
    build_bundle(root, "runs/v0/case-01/t1")
    run_dir = root / "runs/v0/case-01/t1"
    outside_dir = tmp_path / "outside-evidence"
    outside_dir.mkdir()
    (outside_dir / "ev-x.json").write_text("{}", encoding="utf-8")
    shutil.rmtree(run_dir / "evidence")
    os.symlink(outside_dir, run_dir / "evidence", target_is_directory=True)
    manifest_path = _write_single_trial_manifest(root)

    with pytest.raises(ValueError) as excinfo:
        project_studio(manifest_path)

    assert str(outside_dir) not in str(excinfo.value)


def test_evidence_file_symlink_escape_is_refused(tmp_path: Path, build_bundle) -> None:
    root = tmp_path / "escape-evidence-file"
    build_bundle(root, "runs/v0/case-01/t1", with_evidence=True)
    run_dir = root / "runs/v0/case-01/t1"
    outside_file = tmp_path / "outside-ev.json"
    outside_file.write_text("EXTERNAL_EVIDENCE_MARKER", encoding="utf-8")
    target = run_dir / "evidence" / "ev-001.json"
    target.unlink()
    os.symlink(outside_file, target)
    manifest_path = _write_single_trial_manifest(root)

    with pytest.raises(ValueError) as excinfo:
        project_studio(manifest_path)

    message = str(excinfo.value)
    assert str(outside_file) not in message
    assert "EXTERNAL_EVIDENCE_MARKER" not in message
