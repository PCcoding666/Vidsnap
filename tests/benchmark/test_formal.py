"""Deterministic formal benchmark statistics and contracts."""

import pytest

from vidsnap.benchmark.formal import (
    paired_bootstrap_delta,
    parse_mcq_answer,
    superiority_status,
    tool_selection_score,
)


def test_mcq_parser_accepts_one_declared_letter_and_rejects_ambiguous_text() -> None:
    """Broad free-text judging or undeclared options must fail this test."""
    assert parse_mcq_answer("The best answer is: c.", ("A", "B", "C", "D")) == "C"
    assert parse_mcq_answer("B", ("A", "B", "C", "D")) == "B"
    assert parse_mcq_answer("It could be A or B", ("A", "B", "C", "D")) is None
    assert parse_mcq_answer("E", ("A", "B", "C", "D")) is None


def test_paired_bootstrap_is_deterministic_and_uses_strict_superiority_rule() -> None:
    """Changing pairing or allowing a zero CI lower bound to win must fail this test."""
    first = paired_bootstrap_delta(
        [0, 0, 1, 1],
        [1, 1, 1, 1],
        seed=7,
        resamples=1_000,
    )
    second = paired_bootstrap_delta(
        [0, 0, 1, 1],
        [1, 1, 1, 1],
        seed=7,
        resamples=1_000,
    )

    assert first == second
    assert first.point_estimate == 0.5
    assert first.lower <= first.point_estimate <= first.upper
    assert superiority_status(first) == "NOT_YET_SUPERIOR"

    decisive = paired_bootstrap_delta([0] * 54, [1] * 54, seed=7, resamples=1_000)
    assert decisive.lower == 1.0
    assert superiority_status(decisive) == "HARNESS_SUPERIOR"


def test_tool_selection_score_counts_false_and_missed_calls() -> None:
    """Ignoring an extra paid tool or a missed required tool must fail this test."""
    score = tool_selection_score(
        predicted=[
            {"transcribe_audio"},
            {"transcribe_audio", "sample_evidence"},
            set(),
        ],
        expected=[
            {"transcribe_audio"},
            {"sample_evidence"},
            {"transcribe_audio"},
        ],
    )

    assert score.precision == pytest.approx(2 / 3)
    assert score.recall == pytest.approx(2 / 3)
    assert score.f1 == pytest.approx(2 / 3)
    assert score.invalid_calls == 1
    assert score.missed_calls == 1
    assert score.invalid_call_rate == pytest.approx(1 / 3)
    assert score.missed_call_rate == pytest.approx(1 / 3)


def test_bootstrap_rejects_unpaired_or_non_binary_outcomes() -> None:
    with pytest.raises(ValueError, match="same non-zero length"):
        paired_bootstrap_delta([1], [], seed=7)
    with pytest.raises(ValueError, match="binary"):
        paired_bootstrap_delta([2], [1], seed=7)
