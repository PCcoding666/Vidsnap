"""Machine-readable benchmark report aggregation."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import BenchmarkUsage, VariantOutcome
from vidsnap.benchmark.reporting import build_benchmark_report, efficient_noninferiority_passes
from vidsnap.contracts import TerminalState


def _cases() -> list[FormalCase]:
    cases = []
    for index in range(6):
        cases.append(
            FormalCase(
                case_id=f"case-{index}",
                dataset="Video-MME" if index < 4 else "MVBench",
                dataset_version="revision",
                dataset_license="Internal research only.",
                source_url="https://example.invalid/official",
                source=Path(f"/external/video-{index}.mp4"),
                source_sha256=f"{index:x}" * 64,
                task_family="Information Synopsis" if index < 4 else "Action Sequence",
                question="What happens?",
                options={"A": "First", "B": "Second"},
                answer="A",
                has_audio=index % 2 == 0,
                duration_stratum=("short", "medium", "long")[index % 3],
                requirements=(("speech",) if index % 2 == 0 else ("visual",)),
                expected_tools=(("transcribe_audio",) if index % 2 == 0 else ("sample_evidence",)),
                tool_annotation_reason=("speech-required" if index % 2 == 0 else "visual-required"),
            )
        )
    return cases


def _outcome(
    case: FormalCase,
    variant: str,
    *,
    correct: bool,
    calls: int,
    input_bytes: int | None = None,
    input_tokens: int | None = None,
) -> VariantOutcome:
    selected = case.expected_tools if variant == "agentic" else ()
    return VariantOutcome(
        case_id=case.case_id,
        variant=variant,
        terminal_state=TerminalState.SUCCEEDED,
        answer="A" if correct else "B",
        correct=correct,
        selected_tools=selected,
        direct_input_mode="frames_2fps" if variant == "direct" else None,
        usage=BenchmarkUsage(
            model_calls=calls,
            evidence_frames=calls,
            input_bytes=100 * calls if input_bytes is None else input_bytes,
            input_tokens=10 * calls if input_tokens is None else input_tokens,
            output_tokens=calls,
            latency_seconds=0.5 * calls,
        ),
        verifier_gates={
            "schema_valid": True,
            "timestamps_in_bounds": True,
            "referenced_evidence_exists": True,
            "claims_are_supported": True,
            "required_sections_covered": True,
        },
        verifier_passed=True,
    )


def test_smoke_report_uses_paired_metrics_and_measured_54_case_projection() -> None:
    """Unpaired accuracy or guessed formal usage must fail this test."""
    cases = _cases()
    outcomes = []
    fixed_correct = (False, True, False, True, False, True)
    agentic_correct = (True, True, True, True, False, True)
    for index, case in enumerate(cases):
        outcomes.extend(
            [
                _outcome(case, "direct", correct=index % 2 == 0, calls=1),
                _outcome(case, "fixed", correct=fixed_correct[index], calls=2),
                _outcome(case, "agentic", correct=agentic_correct[index], calls=3),
            ]
        )

    report = build_benchmark_report(
        cases,
        outcomes,
        phase="smoke",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )

    assert report["status"] == "SMOKE_SUCCEEDED"
    assert report["benchmark_scope"] == "short_video_only"
    for formal_only_field in (
        "accuracy",
        "paired_accuracy_delta",
        "pre_registered_tool_selection_alignment",
        "verifier_gate_pass_rate",
        "decision_thresholds",
        "provider_input_efficiency",
        "formal_conclusions",
        "conclusion",
    ):
        assert formal_only_field not in report
    assert report["pre_registration_manifest_sha256"] == "f" * 64
    assert report["scope_limitations"] == [
        "MVBench slice covers only Action Sequence; it is not a full MVBench estimate.",
        "Short-video smoke only; it does not validate medium or long videos.",
    ]
    assert report["direct_frame_transport_profile"] == {
        "timeline": "complete",
        "fps": 2,
        "height_pixels": 96,
        "codec": "jpeg",
        "ffmpeg_qscale": 20,
        "provider_min_pixels": 4096,
    }
    assert report["usage"]["agentic"]["model_calls"] == 18
    projection = report["formal_54_case_projection"]
    assert projection["scale_factor"] == 9.0
    assert projection["usage"]["agentic"]["model_calls"] == 162
    assert isinstance(projection["usage"]["agentic"]["model_calls"], int)


def test_smoke_report_discloses_one_videomme_source_for_three_questions() -> None:
    """Reusing one source video must remain visible in the report limitations."""
    cases = _cases()
    cases[3] = cases[3].model_copy(update={"dataset": "MVBench", "task_family": "Action Antonym"})
    cases = [
        case.model_copy(update={"source_sha256": "a" * 64}) if case.dataset == "Video-MME" else case
        for case in cases
    ]
    outcomes = [
        _outcome(case, variant, correct=True, calls=1)
        for case in cases
        for variant in ("direct", "fixed", "agentic")
    ]

    report = build_benchmark_report(
        cases,
        outcomes,
        phase="smoke",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )

    assert (
        "Video-MME slice contains three questions from one source video."
        in report["scope_limitations"]
    )


def test_formal_report_uses_median_provider_input_and_registered_boundaries() -> None:
    """Totals, strict 25% comparisons, or requiring both cost metrics must fail this test."""
    cases = _cases()
    outcomes = []
    for case in cases:
        outcomes.extend(
            [
                _outcome(
                    case,
                    "direct",
                    correct=True,
                    calls=1,
                    input_bytes=200,
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "fixed",
                    correct=True,
                    calls=1,
                    input_bytes=150,
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "agentic",
                    correct=True,
                    calls=2,
                    input_bytes=120,
                    input_tokens=75,
                ),
            ]
        )

    report = build_benchmark_report(
        cases,
        outcomes,
        phase="formal",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )

    assert report["decision_thresholds"] == {
        "paired_accuracy_delta_ci_lower": -0.056,
        "median_provider_input_reduction": 0.25,
    }
    assert report["provider_input_efficiency"] == {
        "fixed_vs_direct": {
            "input_bytes": {
                "baseline_median": 200.0,
                "candidate_median": 150.0,
                "reduction_fraction": 0.25,
            },
            "input_tokens": {
                "baseline_median": 100.0,
                "candidate_median": 100.0,
                "reduction_fraction": 0.0,
            },
            "at_least_25_percent_reduction": True,
        },
        "agentic_vs_fixed": {
            "input_bytes": {
                "baseline_median": 150.0,
                "candidate_median": 120.0,
                "reduction_fraction": 0.2,
            },
            "input_tokens": {
                "baseline_median": 100.0,
                "candidate_median": 75.0,
                "reduction_fraction": 0.25,
            },
            "at_least_25_percent_reduction": True,
        },
    }
    assert report["formal_conclusions"] == {
        "fixed_vs_direct": "FIXED_HARNESS_EFFICIENT_NONINFERIOR",
        "agentic_vs_fixed": "AGENTIC_HARNESS_EFFICIENT_NONINFERIOR",
        "additional_markers": [],
    }
    assert "conclusion" not in report


def test_noninferiority_ci_boundary_is_inclusive() -> None:
    """Changing the registered CI comparison from inclusive to strict must fail this test."""
    assert efficient_noninferiority_passes(
        ci_lower=-0.056,
        has_required_input_reduction=True,
        eligible=True,
    )
    assert not efficient_noninferiority_passes(
        ci_lower=-0.0560001,
        has_required_input_reduction=True,
        eligible=True,
    )
    assert not efficient_noninferiority_passes(
        ci_lower=0.0,
        has_required_input_reduction=False,
        eligible=True,
    )
    assert not efficient_noninferiority_passes(
        ci_lower=0.0,
        has_required_input_reduction=True,
        eligible=False,
    )


def test_formal_efficiency_decision_uses_per_case_median_not_totals() -> None:
    """One huge outlier must affect totals without changing a median-based decision."""
    cases = _cases()
    fixed_bytes = (75, 75, 75, 75, 75, 1000)
    outcomes = []
    for index, case in enumerate(cases):
        outcomes.extend(
            [
                _outcome(
                    case,
                    "direct",
                    correct=True,
                    calls=1,
                    input_bytes=100,
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "fixed",
                    correct=True,
                    calls=1,
                    input_bytes=fixed_bytes[index],
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "agentic",
                    correct=True,
                    calls=2,
                    input_bytes=fixed_bytes[index],
                    input_tokens=100,
                ),
            ]
        )

    report = build_benchmark_report(
        cases,
        outcomes,
        phase="formal",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )

    assert report["usage"]["fixed"]["input_bytes"] == 1375
    assert report["usage"]["direct"]["input_bytes"] == 600
    assert report["provider_input_efficiency"]["fixed_vs_direct"]["input_bytes"] == {
        "baseline_median": 100.0,
        "candidate_median": 75.0,
        "reduction_fraction": 0.25,
    }
    assert report["formal_conclusions"]["fixed_vs_direct"] == (
        "FIXED_HARNESS_EFFICIENT_NONINFERIOR"
    )


def test_formal_efficiency_rejects_total_savings_without_median_savings() -> None:
    """Aggregate savings from one outlier must not satisfy the median efficiency gate."""
    cases = _cases()
    direct_bytes = (100, 100, 100, 100, 100, 1000)
    fixed_bytes = (80, 80, 80, 80, 80, 0)
    outcomes = []
    for index, case in enumerate(cases):
        outcomes.extend(
            [
                _outcome(
                    case,
                    "direct",
                    correct=True,
                    calls=1,
                    input_bytes=direct_bytes[index],
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "fixed",
                    correct=True,
                    calls=1,
                    input_bytes=fixed_bytes[index],
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "agentic",
                    correct=True,
                    calls=2,
                    input_bytes=fixed_bytes[index],
                    input_tokens=100,
                ),
            ]
        )

    report = build_benchmark_report(
        cases,
        outcomes,
        phase="formal",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )

    assert report["usage"]["fixed"]["input_bytes"] == 400
    assert report["usage"]["direct"]["input_bytes"] == 1500
    assert report["provider_input_efficiency"]["fixed_vs_direct"]["input_bytes"] == {
        "baseline_median": 100.0,
        "candidate_median": 80.0,
        "reduction_fraction": 0.2,
    }
    assert report["formal_conclusions"]["fixed_vs_direct"] == "NOT_YET_PROVEN"


def test_formal_noninferiority_and_efficiency_must_both_pass() -> None:
    """Savings cannot hide inferiority, and accuracy parity cannot hide low savings."""
    cases = _cases()
    outcomes = []
    for case in cases:
        outcomes.extend(
            [
                _outcome(
                    case,
                    "direct",
                    correct=True,
                    calls=1,
                    input_bytes=100,
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "fixed",
                    correct=False,
                    calls=1,
                    input_bytes=50,
                    input_tokens=50,
                ),
                _outcome(
                    case,
                    "agentic",
                    correct=False,
                    calls=2,
                    input_bytes=45,
                    input_tokens=45,
                ),
            ]
        )

    accuracy_failed = build_benchmark_report(
        cases,
        outcomes,
        phase="formal",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )
    assert accuracy_failed["paired_accuracy_delta"]["direct_to_fixed"]["lower"] == -1.0
    assert accuracy_failed["formal_conclusions"]["fixed_vs_direct"] == "NOT_YET_PROVEN"

    parity_outcomes = []
    for case in cases:
        parity_outcomes.extend(
            [
                _outcome(
                    case,
                    "direct",
                    correct=True,
                    calls=1,
                    input_bytes=100,
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "fixed",
                    correct=True,
                    calls=1,
                    input_bytes=80,
                    input_tokens=80,
                ),
                _outcome(
                    case,
                    "agentic",
                    correct=True,
                    calls=2,
                    input_bytes=70,
                    input_tokens=70,
                ),
            ]
        )
    efficiency_failed = build_benchmark_report(
        cases,
        parity_outcomes,
        phase="formal",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )
    assert efficiency_failed["paired_accuracy_delta"]["direct_to_fixed"]["lower"] == 0.0
    assert efficiency_failed["formal_conclusions"]["fixed_vs_direct"] == "NOT_YET_PROVEN"


def test_formal_superiority_is_only_an_extra_marker_for_complete_positive_ci() -> None:
    """A positive Agentic CI may add superiority but may not replace registered conclusions."""
    cases = _cases()
    outcomes = []
    for case in cases:
        outcomes.extend(
            [
                _outcome(
                    case,
                    "direct",
                    correct=False,
                    calls=1,
                    input_bytes=200,
                    input_tokens=100,
                ),
                _outcome(
                    case,
                    "fixed",
                    correct=False,
                    calls=1,
                    input_bytes=100,
                    input_tokens=50,
                ),
                _outcome(
                    case,
                    "agentic",
                    correct=True,
                    calls=2,
                    input_bytes=50,
                    input_tokens=25,
                ),
            ]
        )

    report = build_benchmark_report(
        cases,
        outcomes,
        phase="formal",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )

    assert report["paired_accuracy_delta"]["fixed_to_agentic"]["lower"] == 1.0
    assert report["formal_conclusions"]["agentic_vs_fixed"] == (
        "AGENTIC_HARNESS_EFFICIENT_NONINFERIOR"
    )
    assert report["formal_conclusions"]["additional_markers"] == ["HARNESS_SUPERIOR"]


@pytest.mark.parametrize(
    "ineligible_state",
    (TerminalState.PARTIAL, TerminalState.NO_OP, TerminalState.FAILED),
)
def test_ineligible_run_can_never_claim_harness_superior(
    ineligible_state: TerminalState,
) -> None:
    """A positive CI cannot override an incomplete or unverified path."""
    cases = _cases()
    outcomes = []
    for index, case in enumerate(cases):
        direct = _outcome(case, "direct", correct=True, calls=1)
        if index == 0:
            direct = direct.model_copy(
                update={
                    "terminal_state": ineligible_state,
                    "verifier_passed": False,
                }
            )
        outcomes.extend(
            [
                direct,
                _outcome(case, "fixed", correct=False, calls=1),
                _outcome(case, "agentic", correct=True, calls=2),
            ]
        )

    report = build_benchmark_report(
        cases,
        outcomes,
        phase="formal",
        seed=20260812,
        direct_input_mode="frames_2fps",
        pre_registration_manifest_sha256="f" * 64,
    )

    assert report["paired_accuracy_delta"]["fixed_to_agentic"]["lower"] == 1.0
    assert report["status"] == "PARTIAL"
    assert report["formal_conclusions"] == {
        "fixed_vs_direct": "NOT_YET_PROVEN",
        "agentic_vs_fixed": "NOT_YET_PROVEN",
        "additional_markers": [],
    }
