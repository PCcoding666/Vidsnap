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
) -> dict[str, object]:
    """Build the pre-registered report and strict superiority conclusion."""
    if not cases:
        raise ValueError("benchmark report requires cases")
    if len(outcomes) != len(cases) * 3:
        raise ValueError("benchmark report requires three outcomes per case")
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
    report: dict[str, object] = {
        "phase": phase,
        "status": status,
        "model": QWEN_MODEL,
        "case_count": len(cases),
        "dataset_counts": dict(sorted(Counter(case.dataset for case in cases).items())),
        "direct_input_mode": direct_input_mode,
        "accuracy": {
            variant: sum(item.correct for item in items) / len(items)
            for variant, items in grouped.items()
        },
        "paired_accuracy_delta": {
            "direct_to_fixed": asdict(direct_to_fixed),
            "fixed_to_agentic": asdict(fixed_to_agentic),
        },
        "tool_selection": asdict(tool_score),
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
                "duration_stratum": case.duration_stratum,
                "has_audio": case.has_audio,
                "requirements": list(case.requirements),
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
