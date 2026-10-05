"""Exact deterministic trust metrics over registered benchmark cases."""

from __future__ import annotations

import socket

import pytest

from vidsnap.benchmark.trust import (
    RegisteredCase,
    RepetitionObservation,
    TrustManifest,
    TrustMeasurement,
    TrustOutcome,
    TrustReport,
    evaluate_trust,
)

VARIANTS = ("direct", "harness")

METRIC_NAMES = (
    "temporal_grounding",
    "citation_precision",
    "unsupported_claim_rate",
    "evidence_coverage",
    "tool_budget_compliance",
    "provider_regression",
    "latency",
    "cost",
    "replay_determinism",
)

UNKNOWN_METRIC_NAMES = (
    "temporal_grounding",
    "citation_precision",
    "provider_regression",
    "cost",
    "replay_determinism",
)

CAP_EXCEEDED = {"model_calls": 3, "tool_calls": 4, "evidence_frames": 7}


def _hex64(tag: int) -> str:
    return f"{tag:064x}"


def _case() -> RegisteredCase:
    return RegisteredCase(
        case_id="case-0",
        source_sha256=_hex64(1),
        input_fingerprint=_hex64(2),
        transcript_condition="verified",
        transcript_fingerprint=_hex64(3),
        model="qwen3.8-max",
        dataset="Video-MME",
        dataset_version="revision",
        available_evidence_fingerprint=_hex64(4),
        declared_evidence_fingerprints=(_hex64(4), _hex64(5)),
        baseline_result_fingerprint=_hex64(20),
        max_model_calls=2,
        max_tool_calls=3,
        max_evidence_frames=6,
    )


def _measurement(**overrides: object) -> TrustMeasurement:
    values: dict[str, object] = {
        "temporal_observations": (
            ((0.0, 10.0), (5.0, 15.0)),
            ((0.0, 4.0), (0.0, 4.0)),
        ),
        "citations_total": 4,
        "citations_resolved": 3,
        "claims_total": 4,
        "claims_unsupported": 1,
        "claims_with_evidence": 3,
        "model_calls": 2,
        "tool_calls": 3,
        "evidence_frames": 6,
        "latency_seconds": 2.5,
        "cost_usd": 0.012,
        "result_fingerprint": _hex64(20),
        "trace_fingerprint": _hex64(21),
        "repetitions": (
            RepetitionObservation(result_fingerprint=_hex64(30), trace_fingerprint=_hex64(31)),
            RepetitionObservation(result_fingerprint=_hex64(30), trace_fingerprint=_hex64(31)),
        ),
    }
    values.update(overrides)
    return TrustMeasurement(**values)


def _outcome(variant: str, measurement: TrustMeasurement | None) -> TrustOutcome:
    case = _case()
    declared = case.declared_evidence_fingerprints
    return TrustOutcome(
        case_id=case.case_id,
        variant=variant,
        source_sha256=case.source_sha256,
        input_fingerprint=case.input_fingerprint,
        transcript_condition=case.transcript_condition,
        transcript_fingerprint=case.transcript_fingerprint,
        model=case.model,
        dataset=case.dataset,
        dataset_version=case.dataset_version,
        available_evidence_fingerprint=case.available_evidence_fingerprint,
        used_evidence_fingerprints=(
            declared if variant == "harness" else (case.available_evidence_fingerprint,)
        ),
        measurement=measurement,
    )


def _report() -> TrustReport:
    manifest = TrustManifest(registered_cases=(_case(),), variants=VARIANTS)
    return evaluate_trust(
        manifest,
        [_outcome("direct", _measurement()), _outcome("harness", _measurement())],
    )


def _report_with_repetitions(
    repetitions: tuple[RepetitionObservation, ...],
) -> TrustReport:
    manifest = TrustManifest(registered_cases=(_case(),), variants=VARIANTS)
    direct = _outcome("direct", _measurement(repetitions=repetitions))
    harness = _outcome("harness", _measurement(repetitions=repetitions))
    return evaluate_trust(manifest, [direct, harness])


@pytest.mark.parametrize("field", sorted(CAP_EXCEEDED))
def test_exceeding_any_registered_cap_makes_compliance_zero(field: str) -> None:
    """Exceeding any single registered cap must zero the compliance metric."""
    manifest = TrustManifest(registered_cases=(_case(),), variants=VARIANTS)
    outcomes = [_outcome("direct", _measurement()), _outcome("harness", _measurement())]
    outcomes[1] = outcomes[1].model_copy(
        update={"measurement": _measurement(**{field: CAP_EXCEEDED[field]})}
    )

    harness = evaluate_trust(manifest, outcomes).metrics["harness"]

    assert harness.tool_budget_compliance.value == 0.0
    assert harness.tool_budget_compliance.denominator == 1


def test_metrics_expose_exact_names_and_status_for_both_variants() -> None:
    report = _report()

    assert set(type(report.metrics["harness"]).model_fields) == set(METRIC_NAMES)
    for variant in VARIANTS:
        for name in METRIC_NAMES:
            metric = getattr(report.metrics[variant], name)
            assert metric.status == "measured"
            assert metric.value is not None
            assert metric.denominator >= 1


def test_metrics_expose_exact_harness_values() -> None:
    harness = _report().metrics["harness"]

    assert harness.temporal_grounding.value == 2 / 3
    assert harness.temporal_grounding.denominator == 2
    assert harness.citation_precision.value == 0.75
    assert harness.citation_precision.numerator == 3
    assert harness.citation_precision.denominator == 4
    assert harness.unsupported_claim_rate.value == 0.25
    assert harness.unsupported_claim_rate.numerator == 1
    assert harness.unsupported_claim_rate.denominator == 4
    assert harness.evidence_coverage.value == 0.75
    assert harness.evidence_coverage.numerator == 3
    assert harness.evidence_coverage.denominator == 4
    assert harness.tool_budget_compliance.value == 1.0
    assert harness.tool_budget_compliance.denominator == 1
    assert harness.provider_regression.value == 0.0
    assert harness.provider_regression.denominator == 1
    assert harness.latency.value == 2.5
    assert harness.latency.total == 2.5
    assert harness.latency.denominator == 1
    assert harness.cost.value == 0.012
    assert harness.cost.total == 0.012
    assert harness.cost.denominator == 1
    assert harness.replay_determinism.value == 1.0
    assert harness.replay_determinism.denominator == 1


def test_replay_determinism_zero_when_only_result_fingerprint_differs() -> None:
    report = _report_with_repetitions(
        (
            RepetitionObservation(result_fingerprint=_hex64(30), trace_fingerprint=_hex64(31)),
            RepetitionObservation(result_fingerprint=_hex64(32), trace_fingerprint=_hex64(31)),
        )
    )

    replay = report.metrics["harness"].replay_determinism

    assert replay.value == 0.0
    assert replay.denominator == 1


def test_replay_determinism_zero_when_only_trace_fingerprint_differs() -> None:
    report = _report_with_repetitions(
        (
            RepetitionObservation(result_fingerprint=_hex64(30), trace_fingerprint=_hex64(31)),
            RepetitionObservation(result_fingerprint=_hex64(30), trace_fingerprint=_hex64(33)),
        )
    )

    replay = report.metrics["harness"].replay_determinism

    assert replay.value == 0.0
    assert replay.denominator == 1


def test_missing_data_stays_unknown_and_never_zero() -> None:
    """Absent data must surface as unknown, never as numeric zero."""
    case = _case().model_copy(update={"baseline_result_fingerprint": None})
    manifest = TrustManifest(registered_cases=(case,), variants=VARIANTS)
    outcomes = [_outcome("direct", TrustMeasurement()), _outcome("harness", TrustMeasurement())]

    report = evaluate_trust(manifest, outcomes)

    for name in UNKNOWN_METRIC_NAMES:
        metric = getattr(report.metrics["harness"], name)
        assert metric.value is None
        assert metric.denominator == 0
        assert metric.status == "unknown"


def test_report_carries_exact_infrastructure_sentence() -> None:
    report = _report()

    assert report.summary == (
        "benchmark infrastructure ready; current results are not statistically meaningful."
    )
    assert report.summary in report.canonical_json().decode()


def test_identical_input_is_byte_stable_with_stable_report_sha256() -> None:
    first = _report()
    second = _report()

    assert isinstance(first.canonical_json(), bytes)
    assert first.canonical_json() == second.canonical_json()
    assert first.report_sha256 == second.report_sha256
    assert len(first.report_sha256) == 64
    assert first.report_sha256 == first.report_sha256.lower()
    assert int(first.report_sha256, 16) >= 0


def test_evaluation_needs_no_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbid_socket(*args: object, **kwargs: object) -> None:
        raise AssertionError("trust evaluation must not open sockets")

    monkeypatch.setattr(socket, "socket", _forbid_socket)

    report = _report()

    assert report.metrics["harness"].tool_budget_compliance.value == 1.0
