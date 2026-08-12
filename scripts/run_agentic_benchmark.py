#!/usr/bin/env python3
"""Validate and run the private phased Agentic Video Harness benchmark."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import (
    BenchmarkProviderConfig,
    BenchmarkUsage,
    BenchmarkVariant,
    DirectInputMode,
    FormalBenchmarkEngine,
    QwenFormalClient,
    UnsupportedVideoInput,
    VariantOutcome,
)
from vidsnap.benchmark.reporting import build_benchmark_report
from vidsnap.contracts import TerminalState
from vidsnap.video.probe import FFmpegMediaPort

Phase = Literal["smoke", "formal"]
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> list[FormalCase]:
    if not path.is_absolute():
        raise ValueError("manifest path must be absolute")
    if not path.is_file():
        raise ValueError("benchmark manifest does not exist")
    cases: list[FormalCase] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError("benchmark manifest cannot be read") from error
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            case = FormalCase.model_validate_json(line)
        except ValidationError as error:
            raise ValueError(f"invalid case contract at manifest line {line_number}") from error
        if not case.source.is_absolute() or not case.source.is_file():
            raise ValueError(f"case {case.case_id} has no absolute local video")
        if _sha256(case.source) != case.source_sha256:
            raise ValueError(f"case {case.case_id} video SHA-256 does not match")
        if case.subtitle_path is not None:
            if not case.subtitle_path.is_absolute() or not case.subtitle_path.is_file():
                raise ValueError(f"case {case.case_id} has no absolute local subtitle")
        cases.append(case)
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("case IDs must be unique")
    return cases


def _validate_composition(cases: list[FormalCase], phase: Phase) -> dict[str, int]:
    expected_count = 6 if phase == "smoke" else 54
    if len(cases) != expected_count:
        raise ValueError(f"{phase} manifest must contain exactly {expected_count} cases")
    dataset_counts = Counter(case.dataset for case in cases)
    if phase == "formal" and dataset_counts != {"Video-MME": 36, "MVBench": 18}:
        raise ValueError("formal manifest must contain 36 Video-MME and 18 MVBench cases")
    if phase == "smoke" and set(dataset_counts) != {"Video-MME", "MVBench"}:
        raise ValueError("smoke manifest must include both datasets")
    requirements = {item for case in cases for item in case.requirements}
    if requirements != {"visual", "speech", "temporal"}:
        raise ValueError("manifest must cover visual, speech, and temporal requirements")
    if {case.has_audio for case in cases} != {True, False}:
        raise ValueError("manifest must cover cases with and without audio")
    if {case.duration_stratum for case in cases} != {"short", "medium", "long"}:
        raise ValueError("manifest must cover short, medium, and long durations")
    return dict(sorted(dataset_counts.items()))


def _load_smoke_gate(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file():
        raise ValueError("a successful smoke report is required for the formal phase")
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("smoke report cannot be validated") from error
    if not isinstance(payload, dict) or payload.get("status") != "SMOKE_SUCCEEDED":
        raise ValueError("smoke report is not successful")
    if payload.get("direct_input_mode") not in {"video", "frames_2fps"}:
        raise ValueError("smoke report has no registered Direct input mode")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("smoke", "formal"), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-report", type=Path)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--validate-only", action="store_true")
    return parser


def _unsupported_outcome(
    case: FormalCase,
    *,
    input_bytes: int,
) -> VariantOutcome:
    gates = {
        "schema_valid": False,
        "timestamps_in_bounds": False,
        "referenced_evidence_exists": False,
        "claims_are_supported": False,
        "required_sections_covered": False,
    }
    return VariantOutcome(
        case_id=case.case_id,
        variant="direct",
        terminal_state=TerminalState.FAILED,
        answer=None,
        correct=False,
        direct_input_mode="video",
        usage=BenchmarkUsage(model_calls=1, input_bytes=input_bytes),
        verifier_gates=gates,
        verifier_passed=False,
        failure_reason="complete-video input unsupported for this case",
    )


def _compatibility_probe_case(cases: list[FormalCase]) -> FormalCase:
    """Use the largest registered payload to decide complete-video support."""
    if not cases:
        raise ValueError("compatibility probe requires at least one case")
    return max(cases, key=lambda case: case.source.stat().st_size)


def _complete_video_probe_succeeded(outcome: VariantOutcome) -> bool:
    """Require an actual provider response before registering video support."""
    return (
        outcome.terminal_state in {TerminalState.SUCCEEDED, TerminalState.PARTIAL}
        and outcome.usage.model_calls == 1
    )


async def _run_experiment(
    cases: list[FormalCase],
    *,
    phase: Phase,
    output_dir: Path,
    seed: int,
    formal_direct_mode: DirectInputMode | None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=False)
    config = BenchmarkProviderConfig.from_env()
    engine = FormalBenchmarkEngine(
        media=FFmpegMediaPort(),
        model=QwenFormalClient(config),
    )
    direct_mode: DirectInputMode = formal_direct_mode or "video"
    direct_mode_decided = formal_direct_mode is not None
    compatibility_probe: dict[str, float | int | str] | None = None
    cached_direct: dict[str, VariantOutcome] = {}
    if phase == "smoke" and not direct_mode_decided:
        probe_case = _compatibility_probe_case(cases)
        try:
            probe_outcome = await engine.run_case(
                probe_case,
                variant="direct",
                work_dir=output_dir / "artifacts" / "compatibility" / "direct-video",
                direct_input_mode="video",
            )
        except UnsupportedVideoInput as error:
            compatibility_probe = {
                "status": "complete_video_unsupported",
                "case_id": probe_case.case_id,
                "model_calls": 1,
                "input_bytes": error.input_bytes,
            }
            direct_mode = "frames_2fps"
        else:
            if not _complete_video_probe_succeeded(probe_outcome):
                compatibility_probe = {
                    "status": "complete_video_unusable",
                    "case_id": probe_case.case_id,
                    "model_calls": probe_outcome.usage.model_calls,
                    "input_bytes": probe_outcome.usage.input_bytes,
                    "latency_seconds": probe_outcome.usage.latency_seconds,
                }
                direct_mode = "frames_2fps"
                direct_mode_decided = True
            else:
                compatibility_probe = {
                    "status": "complete_video_supported",
                    "case_id": probe_case.case_id,
                    "model_calls": probe_outcome.usage.model_calls,
                    "input_bytes": probe_outcome.usage.input_bytes,
                    "latency_seconds": probe_outcome.usage.latency_seconds,
                }
                cached_direct[probe_case.case_id] = probe_outcome
                direct_mode = "video"
        direct_mode_decided = True
    indexed_cases = list(enumerate(cases))
    random.Random(seed).shuffle(indexed_cases)
    variant_orders: tuple[tuple[BenchmarkVariant, ...], ...] = (
        ("direct", "fixed", "agentic"),
        ("fixed", "agentic", "direct"),
        ("agentic", "direct", "fixed"),
    )
    outcomes: list[VariantOutcome] = []
    for order_index, (_, case) in enumerate(indexed_cases):
        for variant in variant_orders[order_index % len(variant_orders)]:
            work_dir = output_dir / "artifacts" / f"{order_index:03d}" / variant
            if variant == "direct" and case.case_id in cached_direct:
                outcomes.append(cached_direct.pop(case.case_id))
                continue
            try:
                outcome = await engine.run_case(
                    case,
                    variant=variant,
                    work_dir=work_dir,
                    direct_input_mode=direct_mode,
                )
            except UnsupportedVideoInput as error:
                outcome = _unsupported_outcome(case, input_bytes=error.input_bytes)
            outcomes.append(outcome)

    report = build_benchmark_report(
        cases,
        outcomes,
        phase=phase,
        seed=seed,
        direct_input_mode=direct_mode,
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report["seed"] = seed
    report["runtime"] = {
        "python": platform.python_version(),
        "platform": platform.system(),
    }
    if compatibility_probe is not None:
        report["direct_compatibility_probe"] = compatibility_probe
    outcomes_path = output_dir / "outcomes.jsonl"
    outcomes_path.write_text(
        "".join(
            json.dumps(outcome.model_dump(mode="json"), ensure_ascii=True, sort_keys=True) + "\n"
            for outcome in outcomes
        ),
        encoding="utf-8",
    )
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if _is_within(output_dir, REPOSITORY_ROOT):
        parser.error("benchmark output directory must be outside the repository")
    phase: Phase = args.phase
    smoke_gate: dict[str, object] | None = None
    if phase == "formal":
        try:
            smoke_gate = _load_smoke_gate(args.smoke_report)
        except ValueError as error:
            parser.error(str(error))
    try:
        cases = _load_manifest(args.manifest.resolve())
        dataset_counts = _validate_composition(cases, phase)
    except ValueError as error:
        parser.error(str(error))
    if args.validate_only:
        print(
            json.dumps(
                {
                    "status": "VALIDATED",
                    "phase": phase,
                    "case_count": len(cases),
                    "dataset_counts": dataset_counts,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return
    formal_direct_mode: DirectInputMode | None = None
    if smoke_gate is not None:
        formal_direct_mode = cast(DirectInputMode, smoke_gate["direct_input_mode"])
    try:
        report = asyncio.run(
            _run_experiment(
                cases,
                phase=phase,
                output_dir=output_dir,
                seed=args.seed,
                formal_direct_mode=formal_direct_mode,
            )
        )
    except (OSError, RuntimeError, ValueError):
        parser.error("benchmark runtime configuration or output directory is invalid")
    print(
        json.dumps(
            {
                "status": report["status"],
                "case_count": report["case_count"],
                "conclusion": report["conclusion"],
                "report_path": str(output_dir / "report.json"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    if report["status"] == "SMOKE_FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
