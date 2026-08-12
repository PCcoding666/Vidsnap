"""Aggregate formal outcomes without retaining raw provider responses."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from typing import Literal

from vidsnap.benchmark.formal import (
    FormalCase,
    paired_bootstrap_delta,
    superiority_status,
    tool_selection_score,
)
from vidsnap.benchmark.live import BenchmarkVariant, DirectInputMode, VariantOutcome
from vidsnap.config import QWEN_MODEL
from vidsnap.contracts import TerminalState

BenchmarkPhase = Literal["smoke", "formal"]


def _by_variant(
    outcomes: Sequence[VariantOutcome],
) -> dict[BenchmarkVariant, list[VariantOutcome]]:
    grouped: dict[BenchmarkVariant, list[VariantOutcome]] = {
        "direct": [],
        "fixed": [],
        "agentic": [],
    }
    for outcome in outcomes:
        grouped[outcome.variant].append(outcome)
    return grouped


def _usage_totals(outcomes: Sequence[VariantOutcome]) -> dict[str, int | float]:
    return {
        "model_calls": sum(item.usage.model_calls for item in outcomes),
        "evidence_frames": sum(item.usage.evidence_frames for item in outcomes),
        "input_bytes": sum(item.usage.input_bytes for item in outcomes),
        "input_tokens": sum(item.usage.input_tokens for item in outcomes),
        "output_tokens": sum(item.usage.output_tokens for item in outcomes),
        "latency_seconds": sum(item.usage.latency_seconds for item in outcomes),
    }


def _paired_values(
    cases: Sequence[FormalCase],
    outcomes: Sequence[VariantOutcome],
) -> list[int]:
    by_case = {outcome.case_id: outcome for outcome in outcomes}
    return [int(by_case[case.case_id].correct) for case in cases]


def build_benchmark_report(
    cases: Sequence[FormalCase],
    outcomes: Sequence[VariantOutcome],
    *,
    phase: BenchmarkPhase,
    seed: int,
    direct_input_mode: DirectInputMode,
    pre_registration_manifest_sha256: str,
) -> dict[str, object]:
    """Build the pre-registered report and strict superiority conclusion."""
    if not cases:
        raise ValueError("benchmark report requires cases")
    if len(outcomes) != len(cases) * 3:
        raise ValueError("benchmark report requires three outcomes per case")
    if len(pre_registration_manifest_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in pre_registration_manifest_sha256
    ):
        raise ValueError("pre-registration manifest SHA-256 is invalid")
    expected_pairs = {
        (case.case_id, variant) for case in cases for variant in ("direct", "fixed", "agentic")
    }
    actual_pairs = {(outcome.case_id, outcome.variant) for outcome in outcomes}
    if actual_pairs != expected_pairs:
        raise ValueError("benchmark outcomes do not cover each case and variant exactly once")

    grouped = _by_variant(outcomes)
    direct_values = _paired_values(cases, grouped["direct"])
    fixed_values = _paired_values(cases, grouped["fixed"])
    agentic_values = _paired_values(cases, grouped["agentic"])
    direct_to_fixed = paired_bootstrap_delta(
        direct_values,
        fixed_values,
        seed=seed,
    )
    fixed_to_agentic = paired_bootstrap_delta(
        fixed_values,
        agentic_values,
        seed=seed,
    )
    agentic_by_case = {outcome.case_id: outcome for outcome in grouped["agentic"]}
    tool_score = tool_selection_score(
        [set(agentic_by_case[case.case_id].selected_tools) for case in cases],
        [set(case.expected_tools) for case in cases],
    )
    usage = {variant: _usage_totals(items) for variant, items in grouped.items()}
    failed_states = {TerminalState.BLOCKED, TerminalState.EXHAUSTED, TerminalState.FAILED}
    has_failed_path = any(outcome.terminal_state in failed_states for outcome in outcomes)
    status = (
        ("SMOKE_FAILED" if has_failed_path else "SMOKE_SUCCEEDED")
        if phase == "smoke"
        else ("PARTIAL" if has_failed_path else "COMPLETED")
    )
    mvbench_task_families = sorted(
        {case.task_family for case in cases if case.dataset == "MVBench"}
    )
    scope_limitations = []
    if mvbench_task_families:
        scope_limitations.append(
            "MVBench slice covers only "
            + ", ".join(mvbench_task_families)
            + "; it is not a full MVBench estimate."
        )
    report: dict[str, object] = {
        "phase": phase,
        "status": status,
        "model": QWEN_MODEL,
        "case_count": len(cases),
        "pre_registration_manifest_sha256": pre_registration_manifest_sha256,
        "dataset_counts": dict(sorted(Counter(case.dataset for case in cases).items())),
        "mvbench_task_family_counts": dict(
            sorted(Counter(case.task_family for case in cases if case.dataset == "MVBench").items())
        ),
        "scope_limitations": scope_limitations,
        "direct_input_mode": direct_input_mode,
        "accuracy": {
            variant: sum(item.correct for item in items) / len(items)
            for variant, items in grouped.items()
        },
        "paired_accuracy_delta": {
            "direct_to_fixed": asdict(direct_to_fixed),
            "fixed_to_agentic": asdict(fixed_to_agentic),
        },
        "pre_registered_tool_selection_alignment": asdict(tool_score),
        "usage": usage,
        "verifier_gate_pass_rate": {
            variant: sum(item.verifier_passed for item in items) / len(items)
            for variant, items in grouped.items()
        },
        "conclusion": superiority_status(fixed_to_agentic),
        "case_composition": [
            {
                "case_id": case.case_id,
                "dataset": case.dataset,
                "dataset_version": case.dataset_version,
                "dataset_license": case.dataset_license,
                "source_url": case.source_url,
                "source_sha256": case.source_sha256,
                "task_family": case.task_family,
                "duration_stratum": case.duration_stratum,
                "has_audio": case.has_audio,
                "requirements": list(case.requirements),
                "expected_tools": list(case.expected_tools),
                "tool_annotation_reason": case.tool_annotation_reason,
            }
            for case in cases
        ],
    }
    if phase == "smoke":
        scale_factor = 54 / len(cases)
        report["formal_54_case_projection"] = {
            "basis": "provider-reported six-case smoke usage",
            "scale_factor": scale_factor,
            "usage": {
                variant: {key: value * scale_factor for key, value in totals.items()}
                for variant, totals in usage.items()
            },
        }
    return report
