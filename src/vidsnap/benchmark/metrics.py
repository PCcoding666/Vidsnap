"""Deterministic quality, grounding, and efficiency metrics for benchmark reports."""

from __future__ import annotations

from collections.abc import Sequence


def temporal_iou(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    """Compute intersection-over-union for two inclusive temporal intervals."""
    left_start, left_end = left
    right_start, right_end = right
    if left_end < left_start or right_end < right_start:
        raise ValueError("temporal interval end must not precede start")
    intersection = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    union = max(left_end, right_end) - min(left_start, right_start)
    return intersection / union if union else 1.0


def unsupported_claim_rate(supported: Sequence[bool]) -> float:
    """Return the share of evaluated claims without evidence support."""
    if not supported:
        return 0.0
    return sum(not item for item in supported) / len(supported)


def precision_recall_f1(
    predicted: set[str],
    expected: set[str],
) -> tuple[float, float, float]:
    """Calculate literal-set Fact F1 or event-recall components deterministically."""
    if not predicted and not expected:
        return (1.0, 1.0, 1.0)
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return (precision, recall, f1)


def evidence_coverage(referenced: int, total_claims: int) -> float:
    """Return the fraction of claims that carry at least one evidence reference."""
    if total_claims < 0 or referenced < 0 or referenced > total_claims:
        raise ValueError("invalid evidence coverage counts")
    return referenced / total_claims if total_claims else 1.0
