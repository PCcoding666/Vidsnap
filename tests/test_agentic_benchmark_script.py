"""Local-only benchmark runner safety and phase gates."""

from __future__ import annotations

import asyncio
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


def test_smoke_validate_only_rejects_manifest_outside_committed_preregistration(tmp_path) -> None:
    """A composition-valid but unregistered manifest must fail before execution."""
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

    assert result.returncode == 2
    assert "committed pre-registration" in result.stderr


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


def test_formal_validate_only_rejects_unregistered_multi_task_manifest(tmp_path) -> None:
    """Aggregate task coverage cannot substitute for the committed preregistration."""
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

    assert result.returncode == 2
    assert "committed pre-registration" in result.stderr


def test_smoke_starts_with_registered_frame_sequence_without_video_probe(tmp_path) -> None:
    """A complete-video attempt would violate the selected Qwen 3.8 Direct contract."""
    from vidsnap.benchmark.live import BenchmarkUsage, VariantOutcome
    from vidsnap.contracts import TerminalState

    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")
    cases = namespace["_load_manifest"](_write_smoke_manifest(tmp_path))
    calls: list[tuple[str, str]] = []

    class FakeConfig:
        @classmethod
        def from_env(cls):
            return object()

    class FakeEngine:
        def __init__(self, *, media, model) -> None:
            del media, model

        async def run_case(self, case, *, variant, work_dir, direct_input_mode):
            del work_dir
            calls.append((variant, direct_input_mode))
            return VariantOutcome(
                case_id=case.case_id,
                variant=variant,
                terminal_state=TerminalState.SUCCEEDED,
                answer="A",
                correct=True,
                direct_input_mode=direct_input_mode if variant == "direct" else None,
                usage=BenchmarkUsage(model_calls=1),
                verifier_gates={"schema_valid": True},
                verifier_passed=True,
            )

    def fake_report(cases, outcomes, *, direct_input_mode, **kwargs):
        del outcomes, kwargs
        return {
            "status": "SMOKE_SUCCEEDED",
            "case_count": len(cases),
            "direct_input_mode": direct_input_mode,
        }

    globals_ = namespace["_run_experiment"].__globals__
    globals_["BenchmarkProviderConfig"] = FakeConfig
    globals_["FormalBenchmarkEngine"] = FakeEngine
    globals_["FFmpegMediaPort"] = lambda: object()
    globals_["QwenFormalClient"] = lambda config: config
    globals_["build_benchmark_report"] = fake_report

    report = asyncio.run(
        namespace["_run_experiment"](
            cases,
            phase="smoke",
            output_dir=tmp_path / "smoke-output",
            seed=20260812,
            formal_direct_mode=None,
            pre_registration_manifest_sha256="a" * 64,
        )
    )

    assert report["direct_input_mode"] == "frames_2fps"
    assert "direct_compatibility_probe" not in report
    assert len(calls) == 18
    assert all(mode == "frames_2fps" for _, mode in calls)


def test_formal_composition_rejects_single_mvbench_task_family(tmp_path) -> None:
    """Eighteen action-antonym rows must not pass as broad MVBench coverage."""
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")
    smoke_cases = namespace["_load_manifest"](_write_smoke_manifest(tmp_path))
    formal_cases = []
    for index in range(54):
        original = smoke_cases[index % len(smoke_cases)]
        dataset = "Video-MME" if index < 36 else "MVBench"
        formal_cases.append(
            original.model_copy(
                update={
                    "case_id": f"formal-{index}",
                    "dataset": dataset,
                    "task_family": ("Information Synopsis" if index < 36 else "Action Antonym"),
                    "requirements": (
                        original.requirements if dataset == "Video-MME" else ("visual", "temporal")
                    ),
                }
            )
        )

    with __import__("pytest").raises(ValueError, match="three temporal task families"):
        namespace["_validate_composition"](formal_cases, "formal")


def test_formal_composition_rejects_non_temporal_mvbench_family(tmp_path) -> None:
    """A family name alone must not satisfy temporal-task coverage."""
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")
    smoke_cases = namespace["_load_manifest"](_write_smoke_manifest(tmp_path))
    formal_cases = []
    families = ("Action Antonym", "Action Sequence", "Action Prediction")
    for index in range(54):
        original = smoke_cases[index % len(smoke_cases)]
        dataset = "Video-MME" if index < 36 else "MVBench"
        updates = {
            "case_id": f"formal-{index}",
            "dataset": dataset,
            "task_family": (
                "Information Synopsis" if dataset == "Video-MME" else families[(index - 36) // 6]
            ),
        }
        if dataset == "MVBench" and index == 36:
            updates["requirements"] = ("visual",)
        formal_cases.append(original.model_copy(update=updates))

    with __import__("pytest").raises(ValueError, match="temporal task families"):
        namespace["_validate_composition"](formal_cases, "formal")


def test_smoke_gate_rejects_forged_success_report(tmp_path) -> None:
    """A status string alone must never unlock the formal provider calls."""
    report = tmp_path / "forged-report.json"
    report.write_text(json.dumps({"status": "SMOKE_SUCCEEDED", "direct_input_mode": "frames_2fps"}))
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")

    with __import__("pytest").raises(ValueError, match="smoke report"):
        namespace["_load_smoke_gate"](report)


def test_smoke_cli_summary_has_no_benchmark_conclusion() -> None:
    """Smoke command output must remain a gate status, never a research conclusion."""
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")

    summary = namespace["_terminal_summary"](
        {
            "status": "SMOKE_SUCCEEDED",
            "case_count": 6,
            "formal_conclusions": {"fixed_vs_direct": "FIXED_HARNESS_EFFICIENT_NONINFERIOR"},
        },
        Path("/external/report.json"),
    )

    assert summary == {
        "status": "SMOKE_SUCCEEDED",
        "case_count": 6,
        "report_path": "/external/report.json",
    }


def test_smoke_gate_preserves_hashed_projection_provenance(tmp_path) -> None:
    """A structurally complete gate retains its report digest and measured projection."""
    from vidsnap.benchmark.manifest import REGISTERED_MANIFEST_SHA256
    from vidsnap.config import QWEN_MODEL

    usage = {
        variant: {
            "model_calls": 6,
            "evidence_frames": 12,
            "input_bytes": 1200,
            "input_tokens": 120,
            "output_tokens": 12,
            "latency_seconds": 1.2,
        }
        for variant in ("direct", "fixed", "agentic")
    }
    projection = {
        "basis": "provider-reported six-case smoke usage",
        "scale_factor": 9.0,
        "usage": {
            variant: {field: value * 9 for field, value in totals.items()}
            for variant, totals in usage.items()
        },
    }
    payload = {
        "phase": "smoke",
        "status": "SMOKE_SUCCEEDED",
        "model": QWEN_MODEL,
        "case_count": 6,
        "pre_registration_manifest_sha256": REGISTERED_MANIFEST_SHA256["smoke"],
        "direct_input_mode": "frames_2fps",
        "usage": usage,
        "formal_54_case_projection": projection,
    }
    report = tmp_path / "report.json"
    report.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")

    loaded = namespace["_load_smoke_gate"](report)
    provenance = namespace["_smoke_gate_provenance"](report, loaded)

    assert provenance == {
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "pre_registration_manifest_sha256": REGISTERED_MANIFEST_SHA256["smoke"],
        "direct_input_mode": "frames_2fps",
        "formal_54_case_projection": projection,
    }


def test_smoke_gate_rejects_complete_video_direct_mode(tmp_path) -> None:
    """A legacy video-mode smoke report must not authorize the frames-only protocol."""
    from vidsnap.benchmark.manifest import REGISTERED_MANIFEST_SHA256
    from vidsnap.config import QWEN_MODEL

    usage = {
        variant: {
            "model_calls": 6,
            "evidence_frames": 12,
            "input_bytes": 1200,
            "input_tokens": 120,
            "output_tokens": 12,
            "latency_seconds": 1.2,
        }
        for variant in ("direct", "fixed", "agentic")
    }
    report = tmp_path / "legacy-video-report.json"
    report.write_text(
        json.dumps(
            {
                "phase": "smoke",
                "status": "SMOKE_SUCCEEDED",
                "model": QWEN_MODEL,
                "case_count": 6,
                "pre_registration_manifest_sha256": REGISTERED_MANIFEST_SHA256["smoke"],
                "direct_input_mode": "video",
                "usage": usage,
                "formal_54_case_projection": {
                    "basis": "provider-reported six-case smoke usage",
                    "scale_factor": 9,
                    "usage": {
                        variant: {field: value * 9 for field, value in totals.items()}
                        for variant, totals in usage.items()
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")

    with __import__("pytest").raises(ValueError, match="frames_2fps"):
        namespace["_load_smoke_gate"](report)


def test_smoke_gate_rejects_any_research_conclusion(tmp_path) -> None:
    """A successful smoke artifact containing a conclusion must not authorize formal calls."""
    from vidsnap.benchmark.manifest import REGISTERED_MANIFEST_SHA256
    from vidsnap.config import QWEN_MODEL

    usage = {
        variant: {
            "model_calls": 6,
            "evidence_frames": 12,
            "input_bytes": 1200,
            "input_tokens": 120,
            "output_tokens": 12,
            "latency_seconds": 1.2,
        }
        for variant in ("direct", "fixed", "agentic")
    }
    report = tmp_path / "report-with-conclusion.json"
    report.write_text(
        json.dumps(
            {
                "phase": "smoke",
                "status": "SMOKE_SUCCEEDED",
                "model": QWEN_MODEL,
                "case_count": 6,
                "pre_registration_manifest_sha256": REGISTERED_MANIFEST_SHA256["smoke"],
                "direct_input_mode": "frames_2fps",
                "usage": usage,
                "formal_54_case_projection": {
                    "basis": "provider-reported six-case smoke usage",
                    "scale_factor": 9,
                    "usage": {
                        variant: {field: value * 9 for field, value in totals.items()}
                        for variant, totals in usage.items()
                    },
                },
                "formal_conclusions": {"fixed_vs_direct": "FIXED_HARNESS_EFFICIENT_NONINFERIOR"},
            }
        ),
        encoding="utf-8",
    )
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")

    with __import__("pytest").raises(ValueError, match="must not contain.*conclusion"):
        namespace["_load_smoke_gate"](report)


def test_smoke_gate_rejects_formal_only_research_metrics(tmp_path) -> None:
    """A smoke report carrying accuracy comparisons must not authorize formal calls."""
    from vidsnap.benchmark.manifest import REGISTERED_MANIFEST_SHA256
    from vidsnap.config import QWEN_MODEL

    usage = {
        variant: {
            "model_calls": 6,
            "evidence_frames": 12,
            "input_bytes": 1200,
            "input_tokens": 120,
            "output_tokens": 12,
            "latency_seconds": 1.2,
        }
        for variant in ("direct", "fixed", "agentic")
    }
    report = tmp_path / "report-with-accuracy.json"
    report.write_text(
        json.dumps(
            {
                "phase": "smoke",
                "status": "SMOKE_SUCCEEDED",
                "model": QWEN_MODEL,
                "case_count": 6,
                "pre_registration_manifest_sha256": REGISTERED_MANIFEST_SHA256["smoke"],
                "direct_input_mode": "frames_2fps",
                "usage": usage,
                "formal_54_case_projection": {
                    "basis": "provider-reported six-case smoke usage",
                    "scale_factor": 9,
                    "usage": {
                        variant: {field: value * 9 for field, value in totals.items()}
                        for variant, totals in usage.items()
                    },
                },
                "accuracy": {"direct": 1.0, "fixed": 1.0, "agentic": 1.0},
            }
        ),
        encoding="utf-8",
    )
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")

    with __import__("pytest").raises(ValueError, match="formal-only research metrics"):
        namespace["_load_smoke_gate"](report)


def test_smoke_gate_rejects_projection_not_derived_from_measured_usage(tmp_path) -> None:
    """Structurally valid arbitrary projections must not unlock formal calls."""
    from vidsnap.benchmark.manifest import REGISTERED_MANIFEST_SHA256
    from vidsnap.config import QWEN_MODEL

    measured = {
        variant: {
            "model_calls": 6,
            "evidence_frames": 12,
            "input_bytes": 1200,
            "input_tokens": 120,
            "output_tokens": 12,
            "latency_seconds": 1.2,
        }
        for variant in ("direct", "fixed", "agentic")
    }
    projected = {
        variant: {field: value * 9 for field, value in totals.items()}
        for variant, totals in measured.items()
    }
    projected["agentic"]["model_calls"] += 1
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "phase": "smoke",
                "status": "SMOKE_SUCCEEDED",
                "model": QWEN_MODEL,
                "case_count": 6,
                "pre_registration_manifest_sha256": REGISTERED_MANIFEST_SHA256["smoke"],
                "direct_input_mode": "frames_2fps",
                "usage": measured,
                "formal_54_case_projection": {
                    "basis": "provider-reported six-case smoke usage",
                    "scale_factor": 9,
                    "usage": projected,
                },
            }
        ),
        encoding="utf-8",
    )
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")

    with __import__("pytest").raises(ValueError, match="derived from measured usage"):
        namespace["_load_smoke_gate"](report)


def test_formal_preflight_persists_smoke_gate_before_provider_init(tmp_path) -> None:
    """An interrupted formal run must retain which smoke gate authorized it."""
    namespace = runpy.run_path("scripts/run_agentic_benchmark.py")
    provenance = {
        "report_sha256": "a" * 64,
        "pre_registration_manifest_sha256": "b" * 64,
        "direct_input_mode": "frames_2fps",
        "formal_54_case_projection": {"scale_factor": 9},
    }

    class FailingConfig:
        @classmethod
        def from_env(cls):
            raise RuntimeError("provider init stopped for test")

    namespace["_run_experiment"].__globals__["BenchmarkProviderConfig"] = FailingConfig
    output_dir = tmp_path / "formal-output"

    with __import__("pytest").raises(RuntimeError, match="provider init stopped"):
        asyncio.run(
            namespace["_run_experiment"](
                [],
                phase="formal",
                output_dir=output_dir,
                seed=20260812,
                formal_direct_mode="frames_2fps",
                pre_registration_manifest_sha256="c" * 64,
                smoke_gate_provenance=provenance,
            )
        )

    assert json.loads((output_dir / "smoke-gate.json").read_text(encoding="utf-8")) == provenance
