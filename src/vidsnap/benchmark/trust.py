"""Typed trust and fairness models over registered benchmark cases."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Sequence
from statistics import median
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from vidsnap.benchmark.metrics import temporal_iou
from vidsnap.contracts.models import StrictModel

Hex64 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


class RegisteredCase(StrictModel):
    """One registered trust case with provenance, evidence, and caps."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=256)
    source_sha256: Hex64
    input_fingerprint: Hex64
    transcript_condition: str = Field(min_length=1, max_length=64)
    transcript_fingerprint: Hex64
    model: str = Field(min_length=1, max_length=256)
    dataset: str = Field(min_length=1, max_length=256)
    dataset_version: str = Field(min_length=1, max_length=256)
    available_evidence_fingerprint: Hex64
    declared_evidence_fingerprints: tuple[Hex64, ...]
    baseline_result_fingerprint: Hex64 | None = None
    max_model_calls: int | None = Field(default=None, ge=0)
    max_tool_calls: int | None = Field(default=None, ge=0)
    max_evidence_frames: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_declared_evidence(self) -> RegisteredCase:
        if self.available_evidence_fingerprint not in self.declared_evidence_fingerprints:
            raise ValueError("declared evidence must include the available evidence fingerprint")
        return self


class RepetitionObservation(StrictModel):
    """One repeated-run observation used for replay determinism."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    result_fingerprint: Hex64
    trace_fingerprint: Hex64


class TrustMeasurement(StrictModel):
    """Observed run data; every default means missing, never zero."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temporal_observations: tuple[tuple[tuple[float, float], tuple[float, float]], ...] | None = None
    citations_total: int | None = Field(default=None, ge=0)
    citations_resolved: int | None = Field(default=None, ge=0)
    claims_total: int | None = Field(default=None, ge=0)
    claims_unsupported: int | None = Field(default=None, ge=0)
    claims_with_evidence: int | None = Field(default=None, ge=0)
    model_calls: int | None = Field(default=None, ge=0)
    tool_calls: int | None = Field(default=None, ge=0)
    evidence_frames: int | None = Field(default=None, ge=0)
    latency_seconds: float | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    result_fingerprint: Hex64 | None = None
    trace_fingerprint: Hex64 | None = None
    repetitions: tuple[RepetitionObservation, ...] = ()


class TrustOutcome(StrictModel):
    """One per-case, per-variant outcome carrying registered fairness fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=256)
    variant: str = Field(min_length=1, max_length=64)
    source_sha256: Hex64
    input_fingerprint: Hex64
    transcript_condition: str = Field(min_length=1, max_length=64)
    transcript_fingerprint: Hex64
    model: str = Field(min_length=1, max_length=256)
    dataset: str = Field(min_length=1, max_length=256)
    dataset_version: str = Field(min_length=1, max_length=256)
    available_evidence_fingerprint: Hex64
    used_evidence_fingerprints: tuple[Hex64, ...]
    measurement: TrustMeasurement | None = None


class TrustManifest(StrictModel):
    """Write-once registration of cases and variants sealed by content hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    registered_cases: tuple[RegisteredCase, ...] = Field(min_length=1)
    variants: tuple[str, ...] = Field(min_length=1)
    manifest_sha256: Hex64 | None = None

    @model_validator(mode="after")
    def seal(self) -> TrustManifest:
        if self.manifest_sha256 is None:
            payload = self.model_dump(exclude={"manifest_sha256"}, mode="json")
            computed = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
            object.__setattr__(self, "manifest_sha256", computed)
        return self


class TrustMetricValue(StrictModel):
    """One metric as measured or unknown, with optional parts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["measured", "unknown"]
    value: float | None = None
    numerator: int | None = None
    total: float | None = None
    denominator: int = Field(default=0, ge=0)


class TrustVariantMetrics(StrictModel):
    """Exactly the nine registered trust metrics for one variant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temporal_grounding: TrustMetricValue
    citation_precision: TrustMetricValue
    unsupported_claim_rate: TrustMetricValue
    evidence_coverage: TrustMetricValue
    tool_budget_compliance: TrustMetricValue
    provider_regression: TrustMetricValue
    latency: TrustMetricValue
    cost: TrustMetricValue
    replay_determinism: TrustMetricValue


class TrustReport(StrictModel):
    """Deterministic trust report over a sealed manifest and paired outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    metrics: dict[str, TrustVariantMetrics]
    outcomes: tuple[TrustOutcome, ...]
    report_sha256: Hex64

    def __iter__(self) -> Iterator[TrustOutcome]:  # type: ignore[override]
        return iter(self.outcomes)

    def canonical_json(self) -> bytes:
        payload = self.model_dump(exclude={"report_sha256"}, mode="json")
        return _canonical_json_bytes(payload)


class TrustEvaluationInput(StrictModel):
    """Strict offline evaluation envelope: one sealed manifest and its outcomes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: TrustManifest
    outcomes: tuple[TrustOutcome, ...]


_FAIRNESS_FIELDS = (
    "case_id",
    "source_sha256",
    "input_fingerprint",
    "transcript_condition",
    "transcript_fingerprint",
    "model",
    "dataset",
    "dataset_version",
    "available_evidence_fingerprint",
)


def _sealed_payload_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _validate_manifest_seal(manifest: TrustManifest) -> None:
    payload = manifest.model_dump(exclude={"manifest_sha256"}, mode="json")
    if manifest.manifest_sha256 != _sealed_payload_sha256(payload):
        raise ValueError("manifest_sha256 does not match the registered cases and variants")


def _validate_registration(manifest: TrustManifest) -> None:
    case_ids = [case.case_id for case in manifest.registered_cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("registered case_ids must be unique")
    if len(set(manifest.variants)) != len(manifest.variants):
        raise ValueError("manifest variants must be unique")


def _validate_outcome_coverage(
    manifest: TrustManifest, outcomes: Sequence[TrustOutcome]
) -> dict[tuple[str, str], TrustOutcome]:
    expected = {
        (case.case_id, variant)
        for case in manifest.registered_cases
        for variant in manifest.variants
    }
    seen: dict[tuple[str, str], TrustOutcome] = {}
    for outcome in outcomes:
        key = (outcome.case_id, outcome.variant)
        if key in seen:
            raise ValueError(
                f"duplicate outcome for case {outcome.case_id!r} variant {outcome.variant!r}"
            )
        seen[key] = outcome
    missing = sorted(expected - seen.keys())
    if missing:
        raise ValueError(f"missing outcomes for {missing}")
    extra = sorted(seen.keys() - expected)
    if extra:
        raise ValueError(f"unexpected outcomes for {extra}")
    return seen


def _validate_fairness_fields(
    manifest: TrustManifest, outcomes_by_key: dict[tuple[str, str], TrustOutcome]
) -> None:
    cases = {case.case_id: case for case in manifest.registered_cases}
    for (case_id, _variant), outcome in outcomes_by_key.items():
        case = cases[case_id]
        for field in _FAIRNESS_FIELDS:
            if getattr(outcome, field) != getattr(case, field):
                raise ValueError(f"outcome field {field!r} drifts from registered case {case_id!r}")


def _validate_used_evidence(
    manifest: TrustManifest, outcomes_by_key: dict[tuple[str, str], TrustOutcome]
) -> None:
    cases = {case.case_id: case for case in manifest.registered_cases}
    for (case_id, _variant), outcome in outcomes_by_key.items():
        declared = set(cases[case_id].declared_evidence_fingerprints)
        used = set(outcome.used_evidence_fingerprints)
        if not used <= declared:
            raise ValueError(f"case {case_id!r} uses undeclared evidence fingerprints")


def _normalized_outcomes(
    manifest: TrustManifest, outcomes_by_key: dict[tuple[str, str], TrustOutcome]
) -> tuple[TrustOutcome, ...]:
    return tuple(
        outcomes_by_key[(case.case_id, variant)]
        for case in manifest.registered_cases
        for variant in manifest.variants
    )


def _unknown_metric() -> TrustMetricValue:
    return TrustMetricValue(status="unknown")


def _temporal_grounding(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
) -> TrustMetricValue:
    scores: list[float] = []
    for _case, outcome in pairs:
        measurement = outcome.measurement
        if measurement is None or measurement.temporal_observations is None:
            continue
        for predicted, reference in measurement.temporal_observations:
            scores.append(temporal_iou(predicted, reference))
    if not scores:
        return _unknown_metric()
    return TrustMetricValue(
        status="measured",
        value=sum(scores) / len(scores),
        denominator=len(scores),
    )


def _count_ratio_metric(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
    *,
    label: str,
    numerator_of: Callable[[TrustMeasurement], int | None],
    denominator_of: Callable[[TrustMeasurement], int | None],
    empty_total_value: float,
) -> TrustMetricValue:
    numerator = 0
    denominator = 0
    eligible = 0
    for _case, outcome in pairs:
        measurement = outcome.measurement
        if measurement is None:
            continue
        pair_numerator = numerator_of(measurement)
        pair_denominator = denominator_of(measurement)
        if pair_numerator is None or pair_denominator is None:
            continue
        if pair_numerator > pair_denominator:
            raise ValueError(f"{label}: numerator cannot exceed its total")
        eligible += 1
        numerator += pair_numerator
        denominator += pair_denominator
    if not eligible:
        return _unknown_metric()
    if denominator == 0:
        return TrustMetricValue(
            status="measured",
            value=empty_total_value,
            numerator=0,
            total=0,
            denominator=0,
        )
    return TrustMetricValue(
        status="measured",
        value=numerator / denominator,
        numerator=numerator,
        total=denominator,
        denominator=denominator,
    )


def _citation_precision(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
) -> TrustMetricValue:
    return _count_ratio_metric(
        pairs,
        label="citation_precision",
        numerator_of=lambda measurement: measurement.citations_resolved,
        denominator_of=lambda measurement: measurement.citations_total,
        empty_total_value=1.0,
    )


def _unsupported_claim_rate(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
) -> TrustMetricValue:
    return _count_ratio_metric(
        pairs,
        label="unsupported_claim_rate",
        numerator_of=lambda measurement: measurement.claims_unsupported,
        denominator_of=lambda measurement: measurement.claims_total,
        empty_total_value=0.0,
    )


def _evidence_coverage(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
) -> TrustMetricValue:
    return _count_ratio_metric(
        pairs,
        label="evidence_coverage",
        numerator_of=lambda measurement: measurement.claims_with_evidence,
        denominator_of=lambda measurement: measurement.claims_total,
        empty_total_value=1.0,
    )


def _int_triple(
    first: int | None, second: int | None, third: int | None
) -> tuple[int, int, int] | None:
    if first is None or second is None or third is None:
        return None
    return (first, second, third)


def _tool_budget_compliance(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
) -> TrustMetricValue:
    compliant = 0
    eligible = 0
    for case, outcome in pairs:
        measurement = outcome.measurement
        if measurement is None:
            continue
        caps = _int_triple(case.max_model_calls, case.max_tool_calls, case.max_evidence_frames)
        usage = _int_triple(
            measurement.model_calls, measurement.tool_calls, measurement.evidence_frames
        )
        if caps is None or usage is None:
            continue
        eligible += 1
        if all(used <= cap for used, cap in zip(usage, caps)):
            compliant += 1
    if not eligible:
        return _unknown_metric()
    return TrustMetricValue(
        status="measured",
        value=compliant / eligible,
        numerator=compliant,
        denominator=eligible,
    )


def _provider_regression(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
) -> TrustMetricValue:
    mismatched = 0
    eligible = 0
    for case, outcome in pairs:
        measurement = outcome.measurement
        if measurement is None or case.baseline_result_fingerprint is None:
            continue
        if measurement.result_fingerprint is None:
            continue
        eligible += 1
        if measurement.result_fingerprint != case.baseline_result_fingerprint:
            mismatched += 1
    if not eligible:
        return _unknown_metric()
    return TrustMetricValue(
        status="measured",
        value=mismatched / eligible,
        numerator=mismatched,
        denominator=eligible,
    )


def _median_total_metric(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
    *,
    value_of: Callable[[TrustMeasurement], float | None],
) -> TrustMetricValue:
    values: list[float] = []
    for _case, outcome in pairs:
        measurement = outcome.measurement
        if measurement is None:
            continue
        observed = value_of(measurement)
        if observed is not None:
            values.append(observed)
    if not values:
        return _unknown_metric()
    return TrustMetricValue(
        status="measured",
        value=median(values),
        total=sum(values),
        denominator=len(values),
    )


def _latency(pairs: Sequence[tuple[RegisteredCase, TrustOutcome]]) -> TrustMetricValue:
    return _median_total_metric(pairs, value_of=lambda measurement: measurement.latency_seconds)


def _cost(pairs: Sequence[tuple[RegisteredCase, TrustOutcome]]) -> TrustMetricValue:
    return _median_total_metric(pairs, value_of=lambda measurement: measurement.cost_usd)


def _replay_determinism(
    pairs: Sequence[tuple[RegisteredCase, TrustOutcome]],
) -> TrustMetricValue:
    deterministic = 0
    eligible = 0
    for _case, outcome in pairs:
        measurement = outcome.measurement
        if measurement is None or len(measurement.repetitions) < 2:
            continue
        first = measurement.repetitions[0]
        eligible += 1
        if all(
            repetition.result_fingerprint == first.result_fingerprint
            and repetition.trace_fingerprint == first.trace_fingerprint
            for repetition in measurement.repetitions
        ):
            deterministic += 1
    if not eligible:
        return _unknown_metric()
    return TrustMetricValue(
        status="measured",
        value=deterministic / eligible,
        numerator=deterministic,
        denominator=eligible,
    )


def evaluate_trust(manifest: TrustManifest, outcomes: Sequence[TrustOutcome]) -> TrustReport:
    """Validate registered fairness, then evaluate metrics over the sealed manifest."""
    _validate_manifest_seal(manifest)
    _validate_registration(manifest)
    outcomes_by_key = _validate_outcome_coverage(manifest, outcomes)
    _validate_fairness_fields(manifest, outcomes_by_key)
    _validate_used_evidence(manifest, outcomes_by_key)
    normalized = _normalized_outcomes(manifest, outcomes_by_key)
    metrics: dict[str, TrustVariantMetrics] = {}
    for variant in manifest.variants:
        pairs = [
            (case, outcomes_by_key[(case.case_id, variant)]) for case in manifest.registered_cases
        ]
        metrics[variant] = TrustVariantMetrics(
            temporal_grounding=_temporal_grounding(pairs),
            citation_precision=_citation_precision(pairs),
            unsupported_claim_rate=_unsupported_claim_rate(pairs),
            evidence_coverage=_evidence_coverage(pairs),
            tool_budget_compliance=_tool_budget_compliance(pairs),
            provider_regression=_provider_regression(pairs),
            latency=_latency(pairs),
            cost=_cost(pairs),
            replay_determinism=_replay_determinism(pairs),
        )
    report = TrustReport(
        summary="benchmark infrastructure ready; current results are not statistically meaningful.",
        metrics=metrics,
        outcomes=normalized,
        report_sha256="0" * 64,
    )
    digest = hashlib.sha256(report.canonical_json()).hexdigest()
    return report.model_copy(update={"report_sha256": digest})
