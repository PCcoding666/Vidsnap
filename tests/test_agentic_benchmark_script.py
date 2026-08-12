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
                "task_family": "Information Synopsis" if index < 4 else "Action Antonym",
                "question": "What happens?",
                "options": {"A": "First", "B": "Second"},
                "answer": "A",
                "has_audio": index % 2 == 0,
                "duration_stratum": durations[index],
                "requirements": [requirement],
                "expected_tools": expected,
                "tool_annotation_reason": (
                    "speech-required" if requirement == "speech" else "visual-required"
                ),
            }
        )
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return manifest


def _write_formal_manifest(root: Path) -> Path:
    smoke_rows = [
        json.loads(line)
        for line in _write_smoke_manifest(root).read_text(encoding="utf-8").splitlines()
    ]
    rows = []
    mvbench_families = ("Action Antonym", "Action Sequence", "Action Prediction")
    for index in range(54):
        row = dict(smoke_rows[index % len(smoke_rows)])
        row["case_id"] = f"formal-{index}"
        if index < 36:
            row["dataset"] = "Video-MME"
            row["task_family"] = "Information Synopsis"
        else:
            row["dataset"] = "MVBench"
            row["task_family"] = mvbench_families[(index - 36) // 6]
        rows.append(row)
    manifest = root / "formal.jsonl"
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
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "mvbench_task_family_counts": {"Action Antonym": 2},
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


def test_formal_validate_only_checks_multi_task_manifest_before_smoke(tmp_path) -> None:
    """Offline pre-registration validation must not require a live smoke artifact."""
    manifest = _write_formal_manifest(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_agentic_benchmark.py",
            "--phase",
            "formal",
            "--validate-only",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(tmp_path / "formal-results"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["case_count"] == 54
    assert payload["mvbench_task_family_counts"] == {
        "Action Antonym": 6,
        "Action Prediction": 6,
        "Action Sequence": 6,
    }


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


def test_formal_composition_rejects_single_mvbench_task_family(tmp_path) -> None:
    """Eighteen action-antonym rows must not pass as broad MVBench coverage."""
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")
    smoke_cases = namespace["_load_manifest"](_write_smoke_manifest(tmp_path))
    formal_cases = []
    for index in range(54):
        original = smoke_cases[index % len(smoke_cases)]
        formal_cases.append(
            original.model_copy(
                update={
                    "case_id": f"formal-{index}",
                    "dataset": "Video-MME" if index < 36 else "MVBench",
                    "task_family": ("Information Synopsis" if index < 36 else "Action Antonym"),
                }
            )
        )

    with __import__("pytest").raises(ValueError, match="three task families"):
        namespace["_validate_composition"](formal_cases, "formal")
