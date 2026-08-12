"""Local-only benchmark runner safety and phase gates."""

from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path


def _write_smoke_manifest(root: Path) -> Path:
    manifest = root / "smoke.jsonl"
    rows = []
    requirements = ("visual", "speech", "temporal", "visual", "speech", "temporal")
    durations = ("short", "short", "medium", "medium", "long", "long")
    for index in range(6):
        video = root / f"video-{index}.mp4"
        video.write_bytes(f"video-{index}".encode())
        requirement = requirements[index]
        expected = ["transcribe_audio"] if requirement == "speech" else ["sample_evidence"]
        rows.append(
            {
                "case_id": f"case-{index}",
                "dataset": "Video-MME" if index < 4 else "MVBench",
                "dataset_version": "revision",
                "dataset_license": "Internal non-commercial research only.",
                "source_url": "https://example.invalid/official-dataset",
                "source": str(video),
                "source_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                "question": "What happens?",
                "options": {"A": "First", "B": "Second"},
                "answer": "A",
                "has_audio": index % 2 == 0,
                "duration_stratum": durations[index],
                "requirements": [requirement],
                "expected_tools": expected,
            }
        )
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return manifest


def test_runner_rejects_output_inside_repository(tmp_path) -> None:
    """Writing benchmark artifacts into git scope must fail before manifest access."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_agentic_benchmark.py",
            "--phase",
            "smoke",
            "--manifest",
            str(tmp_path / "missing.jsonl"),
            "--output-dir",
            "benchmark-results/attempt",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "outside the repository" in result.stderr


def test_smoke_validate_only_accepts_six_stratified_external_cases(tmp_path) -> None:
    """Changing smoke count or skipping hash checks must fail this test."""
    manifest = _write_smoke_manifest(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_agentic_benchmark.py",
            "--phase",
            "smoke",
            "--validate-only",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(tmp_path / "results"),
            "--seed",
            "20260812",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "case_count": 6,
        "dataset_counts": {"MVBench": 2, "Video-MME": 4},
        "phase": "smoke",
        "status": "VALIDATED",
    }


def test_formal_validation_requires_successful_smoke_report(tmp_path) -> None:
    """Formal provider calls without a completed smoke gate must fail."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_agentic_benchmark.py",
            "--phase",
            "formal",
            "--validate-only",
            "--manifest",
            str(tmp_path / "formal.jsonl"),
            "--output-dir",
            str(tmp_path / "results"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "smoke report" in result.stderr


def test_smoke_compatibility_probe_uses_largest_registered_payload(tmp_path) -> None:
    """A small random first video must not decide complete-video compatibility."""
    manifest = _write_smoke_manifest(tmp_path)
    rows = manifest.read_text(encoding="utf-8").splitlines()
    largest = json.loads(rows[-1])
    largest_path = Path(largest["source"])
    largest_path.write_bytes(b"largest-video-payload")
    largest["source_sha256"] = hashlib.sha256(largest_path.read_bytes()).hexdigest()
    rows[-1] = json.dumps(largest)
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")

    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")
    cases = namespace["_load_manifest"](manifest)

    assert namespace["_compatibility_probe_case"](cases).case_id == "case-5"


def test_failed_complete_video_probe_is_not_registered_as_supported() -> None:
    """A typed failed outcome must force the registered Direct fallback."""
    from vidsnap.benchmark.live import BenchmarkUsage, VariantOutcome
    from vidsnap.contracts import TerminalState

    outcome = VariantOutcome(
        case_id="case",
        variant="direct",
        terminal_state=TerminalState.FAILED,
        correct=False,
        direct_input_mode="video",
        usage=BenchmarkUsage(model_calls=1, input_bytes=123),
        verifier_gates={},
        verifier_passed=False,
        failure_reason="benchmark case failed",
    )
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")

    assert namespace["_complete_video_probe_succeeded"](outcome) is False
