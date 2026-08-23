"""External-only command boundary for the one-shot Direct URL probe."""

from __future__ import annotations

import asyncio
import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from vidsnap.benchmark.url_probe import (
    DIRECT_URL_PROBE_FPS,
    REGISTERED_PROBE_CASE_ID,
    REGISTERED_PROBE_SHA256,
    REGISTERED_PROBE_SOURCE_BYTES,
    DirectUrlProbeResult,
)


def _write_probe_manifest(root: Path) -> tuple[Path, Path]:
    source = root / "registered.mp4"
    with source.open("wb") as handle:
        handle.truncate(REGISTERED_PROBE_SOURCE_BYTES)
    subtitle = root / "registered.srt"
    subtitle.write_text("registered subtitle", encoding="utf-8")
    manifest = root / "smoke.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "case_id": REGISTERED_PROBE_CASE_ID,
                "dataset": "Video-MME",
                "dataset_version": "revision",
                "dataset_license": "Internal non-commercial research only.",
                "source_url": "https://github.com/MME-Benchmarks/Video-MME",
                "source": str(source),
                "source_sha256": REGISTERED_PROBE_SHA256,
                "task_family": "Action Recognition",
                "question": "What happens?",
                "options": {"A": "First", "B": "Second"},
                "answer": "A",
                "subtitle_path": str(subtitle),
                "has_audio": True,
                "duration_stratum": "long",
                "requirements": ["visual", "temporal"],
                "expected_tools": ["sample_evidence"],
                "tool_annotation_reason": "visual-required",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest, source


def _patch_registered_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    subtitle_bytes = b"registered subtitle"
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe.REGISTERED_PROBE_SUBTITLE_SHA256",
        hashlib.sha256(subtitle_bytes).hexdigest(),
    )
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe.REGISTERED_PROBE_SUBTITLE_BYTES",
        len(subtitle_bytes),
    )
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe._sha256_handle",
        lambda handle: REGISTERED_PROBE_SHA256,
    )


def _result(*, status: str) -> DirectUrlProbeResult:
    return DirectUrlProbeResult(
        status=status,
        case_id=REGISTERED_PROBE_CASE_ID,
        source_sha256=REGISTERED_PROBE_SHA256,
        source_bytes=REGISTERED_PROBE_SOURCE_BYTES,
        upload_status="succeeded",
        request_status="succeeded" if status == "PROBE_SUCCEEDED" else "failed",
        model_calls=1,
        serialized_request_bytes=456,
        input_tokens=1234 if status == "PROBE_SUCCEEDED" else 0,
        output_tokens=1 if status == "PROBE_SUCCEEDED" else 0,
        latency_seconds=2.5,
        failure_category=None if status == "PROBE_SUCCEEDED" else "provider_url_resolution",
        next_step=(
            None if status == "PROBE_SUCCEEDED" else "verify_documented_oss_resolution_contract"
        ),
    )


def test_probe_command_rejects_repository_output_before_manifest_access() -> None:
    """No missing manifest may bypass the repository-output guard."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_direct_url_probe.py",
            "--manifest",
            "/missing/manifest.jsonl",
            "--output-dir",
            str(Path.cwd() / "diagnostic-results" / "attempt"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "outside every git worktree" in result.stderr
    assert "/missing/manifest.jsonl" not in result.stderr


def test_probe_command_rejects_relative_paths_before_resolution() -> None:
    """Relative input or output must not be silently normalized into the live boundary."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_direct_url_probe.py",
            "--manifest",
            "relative-smoke.jsonl",
            "--output-dir",
            "relative-result",
            "--validate-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "absolute" in result.stderr


def test_worktree_discovery_failure_blocks_output_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed git lookup must not leave the main checkout unprotected."""
    namespace = runpy.run_path("scripts/run_direct_url_probe.py")

    def fail_discovery(*args, **kwargs):
        del args, kwargs
        raise OSError("git unavailable")

    monkeypatch.setattr(subprocess, "run", fail_discovery)

    with pytest.raises(ValueError, match="verify every git worktree"):
        namespace["_assert_external_output"](tmp_path / "result")


def test_probe_loader_binds_registered_manifest_case_and_local_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unregistered manifest or changed local video must stop before output creation."""
    manifest, source = _write_probe_manifest(tmp_path)
    namespace = runpy.run_path("scripts/run_direct_url_probe.py")
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()

    def fake_sha256(path: Path) -> str:
        return manifest_digest if path == manifest else REGISTERED_PROBE_SHA256

    monkeypatch.setitem(namespace, "_sha256", fake_sha256)
    _patch_registered_evidence(monkeypatch)

    case = namespace["_load_probe_case"](
        manifest,
        expected_manifest_sha256=manifest_digest,
    )

    assert case.case_id == REGISTERED_PROBE_CASE_ID
    with pytest.raises(ValueError, match="committed pre-registration"):
        namespace["_load_probe_case"](
            manifest,
            expected_manifest_sha256="0" * 64,
        )
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="registered probe case"):
        namespace["_load_probe_case"](
            manifest,
            expected_manifest_sha256=manifest_digest,
        )


def test_validate_only_summary_has_no_network_or_research_fields(tmp_path: Path) -> None:
    """Validation output must describe only the immutable diagnostic inputs."""
    manifest, _ = _write_probe_manifest(tmp_path)
    namespace = runpy.run_path("scripts/run_direct_url_probe.py")
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    summary = namespace["_validation_summary"](manifest_digest)

    assert summary == {
        "status": "VALIDATED",
        "case_id": REGISTERED_PROBE_CASE_ID,
        "model": "qwen3.8-max",
        "fps": DIRECT_URL_PROBE_FPS,
        "source_sha256": REGISTERED_PROBE_SHA256,
        "source_bytes": REGISTERED_PROBE_SOURCE_BYTES,
        "manifest_sha256": manifest_digest,
    }
    assert not ({"accuracy", "conclusion", "answer", "correct"} & set(summary))


def test_full_validate_only_command_never_reads_provider_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The real command must finish validation before any provider object can be created."""
    manifest, _ = _write_probe_manifest(tmp_path)
    namespace = runpy.run_path("scripts/run_direct_url_probe.py")
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    subtitle_bytes = b"registered subtitle"

    def fake_sha256(path: Path) -> str:
        return manifest_digest if path == manifest else REGISTERED_PROBE_SHA256

    class BombConfig:
        @classmethod
        def from_env(cls):
            raise AssertionError("validate-only accessed provider configuration")

    class BombClient:
        def __init__(self, config) -> None:
            del config
            raise AssertionError("validate-only created a provider client")

    namespace["_sha256"] = fake_sha256
    namespace["BenchmarkProviderConfig"] = BombConfig
    namespace["DirectUrlProbeClient"] = BombClient
    monkeypatch.setitem(namespace["REGISTERED_MANIFEST_SHA256"], "smoke", manifest_digest)
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe.REGISTERED_PROBE_SUBTITLE_SHA256",
        hashlib.sha256(subtitle_bytes).hexdigest(),
    )
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe.REGISTERED_PROBE_SUBTITLE_BYTES",
        len(subtitle_bytes),
    )
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe._sha256_handle",
        lambda handle: REGISTERED_PROBE_SHA256,
    )
    output_dir = tmp_path / "validate-only-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_direct_url_probe.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
            "--validate-only",
        ],
    )

    namespace["main"]()

    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "VALIDATED"
    assert not output_dir.exists()


def test_probe_execution_writes_only_sanitized_external_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Temporary transport data or model answers must never reach disk or terminal summary."""
    manifest, _ = _write_probe_manifest(tmp_path)
    namespace = runpy.run_path("scripts/run_direct_url_probe.py")
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()

    def fake_sha256(path: Path) -> str:
        return manifest_digest if path == manifest else REGISTERED_PROBE_SHA256

    namespace["_sha256"] = fake_sha256
    _patch_registered_evidence(monkeypatch)
    case = namespace["_load_probe_case"](
        manifest,
        expected_manifest_sha256=manifest_digest,
    )

    class FakeClient:
        async def run(self, supplied_case) -> DirectUrlProbeResult:
            assert supplied_case is case
            return _result(status="PROBE_SUCCEEDED")

    output_dir = tmp_path / "external-result"
    result, report_path = asyncio.run(
        namespace["_execute_probe"](case, output_dir=output_dir, client=FakeClient())
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = namespace["_terminal_summary"](result, report_path)

    assert list(output_dir.iterdir()) == [report_path]
    assert report == result.model_dump(mode="json")
    assert summary == {"status": "PROBE_SUCCEEDED", "report_path": str(report_path)}
    serialized = json.dumps(report) + json.dumps(summary)
    for forbidden in (
        "oss://",
        "Authorization",
        "upload_host",
        "object_key",
        "policy",
        "signature",
        "raw_request",
        "raw_response",
        '"answer"',
        '"accuracy"',
        '"conclusion"',
    ):
        assert forbidden not in serialized


def test_failed_probe_report_is_bounded_and_nonzero_exit(tmp_path: Path) -> None:
    """A provider rejection must persist one safe category and stop the command."""
    namespace = runpy.run_path("scripts/run_direct_url_probe.py")
    result = _result(status="PROBE_FAILED")
    report_path = tmp_path / "report.json"
    namespace["_atomic_json_write"](report_path, result.model_dump(mode="json"))

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["status"] == "PROBE_FAILED"
    assert report["failure_category"] == "provider_url_resolution"
    assert report["next_step"] == "verify_documented_oss_resolution_contract"
    assert namespace["_exit_code"](result) == 1
    assert "oss://" not in report_path.read_text(encoding="utf-8")
