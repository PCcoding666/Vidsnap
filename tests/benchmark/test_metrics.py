"""Deterministic benchmark metrics."""

from vidsnap.benchmark.metrics import temporal_iou, unsupported_claim_rate


def test_deterministic_metrics_cover_temporal_and_grounding_quality() -> None:
    assert temporal_iou((0, 10), (5, 15)) == 1 / 3
    assert unsupported_claim_rate([True, False, False]) == 2 / 3
