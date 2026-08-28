"""Trust and fairness gates over registered benchmark cases."""

from __future__ import annotations

import pytest

from vidsnap.benchmark.trust import (
    RegisteredCase,
    TrustManifest,
    TrustOutcome,
    evaluate_trust,
)

VARIANTS = ("direct", "harness")

FAIRNESS_FIELDS = (
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

MUTATIONS = {
    "case_id": "case-9",
    "source_sha256": "e" * 64,
    "input_fingerprint": "e" * 64,
    "transcript_condition": "raw",
    "transcript_fingerprint": "e" * 64,
    "model": "other-model",
    "dataset": "MVBench",
    "dataset_version": "other-revision",
    "available_evidence_fingerprint": "e" * 64,
}


def _hex64(tag: int) -> str:
    return f"{tag:064x}"


def _cases() -> list[RegisteredCase]:
    return [
        RegisteredCase(
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
        ),
        RegisteredCase(
            case_id="case-1",
            source_sha256=_hex64(6),
            input_fingerprint=_hex64(7),
            transcript_condition="verified",
            transcript_fingerprint=_hex64(8),
            model="qwen3.8-max",
            dataset="MVBench",
            dataset_version="revision",
            available_evidence_fingerprint=_hex64(9),
            declared_evidence_fingerprints=(_hex64(9), _hex64(10)),
        ),
    ]


def _outcome(
    case: RegisteredCase,
    variant: str,
    *,
    evidence: tuple[str, ...] | None = None,
) -> TrustOutcome:
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
            evidence if evidence is not None else (case.available_evidence_fingerprint,)
        ),
    )


def _manifest(cases: list[RegisteredCase], *, sha: str | None = None) -> TrustManifest:
    if sha is None:
        return TrustManifest(registered_cases=tuple(cases), variants=VARIANTS)
    return TrustManifest(
        registered_cases=tuple(cases),
        variants=VARIANTS,
        manifest_sha256=sha,
    )


def _paired_outcomes(cases: list[RegisteredCase]) -> list[TrustOutcome]:
    outcomes = []
    for case in cases:
        outcomes.append(_outcome(case, "direct"))
        outcomes.append(_outcome(case, "harness", evidence=case.declared_evidence_fingerprints))
    return outcomes


def test_accepted_outcomes_match_registered_case_exactly() -> None:
    """Any drift between a registered case and its outcome must fail this test."""
    cases = _cases()
    manifest = _manifest(cases)
    assert manifest.variants == VARIANTS

    trusted = evaluate_trust(manifest, _paired_outcomes(cases))

    for case in cases:
        for variant in VARIANTS:
            outcome = next(
                item for item in trusted if item.case_id == case.case_id and item.variant == variant
            )
            for field in FAIRNESS_FIELDS:
                assert getattr(outcome, field) == getattr(case, field)


def test_duplicate_outcome_raises_value_error() -> None:
    """A second outcome for one case and variant must be rejected."""
    cases = _cases()
    outcomes = _paired_outcomes(cases)
    outcomes.append(outcomes[0].model_copy())

    with pytest.raises(ValueError):
        evaluate_trust(_manifest(cases), outcomes)


def test_missing_outcome_raises_value_error() -> None:
    """Every registered case and declared variant needs exactly one outcome."""
    cases = _cases()
    outcomes = _paired_outcomes(cases)
    del outcomes[2]

    with pytest.raises(ValueError):
        evaluate_trust(_manifest(cases), outcomes)


def test_extra_outcome_raises_value_error() -> None:
    """An outcome outside the registered cases and variants must be rejected."""
    cases = _cases()
    outcomes = _paired_outcomes(cases)
    outcomes.append(_outcome(cases[0], "direct").model_copy(update={"case_id": "case-9"}))

    with pytest.raises(ValueError):
        evaluate_trust(_manifest(cases), outcomes)


@pytest.mark.parametrize("field", sorted(FAIRNESS_FIELDS))
def test_mutated_fairness_field_raises_value_error(field: str) -> None:
    """Outcomes must carry the registered fairness fields without any drift."""
    cases = _cases()
    outcomes = _paired_outcomes(cases)
    outcomes[0] = outcomes[0].model_copy(update={field: MUTATIONS[field]})

    with pytest.raises(ValueError):
        evaluate_trust(_manifest(cases), outcomes)


@pytest.mark.parametrize("variant", VARIANTS)
def test_undeclared_evidence_rejected_for_both_variants(variant: str) -> None:
    """Any used fingerprint outside the shared declared set must be rejected."""
    cases = _cases()
    undeclared = _hex64(11)
    outcomes = _paired_outcomes(cases)
    index = VARIANTS.index(variant)
    outcomes[index] = outcomes[index].model_copy(
        update={
            "used_evidence_fingerprints": (
                cases[0].available_evidence_fingerprint,
                undeclared,
            )
        }
    )

    with pytest.raises(ValueError):
        evaluate_trust(_manifest(cases), outcomes)


def test_stale_manifest_sha_after_case_mutation_raises_value_error() -> None:
    """Mutating a registered case must invalidate the previously sealed manifest."""
    cases = _cases()
    fresh_sha = _manifest(cases).manifest_sha256

    mutated = [cases[0].model_copy(update={"dataset": "MVBench"}), cases[1]]
    stale = _manifest(mutated, sha=fresh_sha)

    with pytest.raises(ValueError):
        evaluate_trust(stale, _paired_outcomes(mutated))
