"""Machine-readable benchmark report aggregation."""

from __future__ import annotations

from pathlib import Path

from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import BenchmarkUsage, VariantOutcome
from vidsnap.benchmark.reporting import build_benchmark_report
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
                question="What happens?",
                options={"A": "First", "B": "Second"},
                answer="A",
                has_audio=index % 2 == 0,
                duration_stratum=("short", "medium", "long")[index % 3],
                requirements=(("speech",) if index % 2 == 0 else ("visual",)),
                expected_tools=(("transcribe_audio",) if index % 2 == 0 else ("sample_evidence",)),
            )
        )
    return cases


def _outcome(
    case: FormalCase,
    variant: str,
    *,
    correct: bool,
    calls: int,
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
            input_bytes=100 * calls,
            input_tokens=10 * calls,
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
    )

    assert report["status"] == "SMOKE_SUCCEEDED"
    assert report["accuracy"] == {
        "agentic": 5 / 6,
        "direct": 0.5,
        "fixed": 0.5,
    }
    assert report["conclusion"] == "NOT_YET_SUPERIOR"
    assert report["tool_selection"]["f1"] == 1.0
    assert report["usage"]["agentic"]["model_calls"] == 18
    projection = report["formal_54_case_projection"]
    assert projection["scale_factor"] == 9.0
    assert projection["usage"]["agentic"]["model_calls"] == 162
