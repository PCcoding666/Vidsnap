"""Deterministic evidence gates used before a run may succeed."""

from __future__ import annotations

from pydantic import Field

from vidsnap.contracts import Claim, Evidence, VideoAnalysisResult
from vidsnap.contracts.models import StrictModel


class VerificationReport(StrictModel):
    """The explicit outcome of checking result claims against captured evidence."""

    passed: bool
    failed_gates: tuple[str, ...] = ()
    targeted_resample_seconds: tuple[tuple[float, float], ...] = Field(default_factory=tuple)


def verify_claims(
    *,
    claims: list[Claim],
    evidence: list[Evidence],
    duration_seconds: float,
    result: VideoAnalysisResult | None = None,
    required_sections: tuple[str, ...] = (),
) -> VerificationReport:
    """Check evidence existence, temporal bounds, support, and required sections."""
    failed_gates: list[str] = []
    targeted_resample_seconds: list[tuple[float, float]] = []

    if duration_seconds < 0:
        failed_gates.append("schema_valid")

    evidence_by_id = {item.id: item for item in evidence}
    if len(evidence_by_id) != len(evidence):
        failed_gates.append("schema_valid")

    out_of_bounds = [
        item for item in evidence if item.start_seconds < 0 or item.end_seconds > duration_seconds
    ]
    if out_of_bounds:
        failed_gates.append("timestamps_in_bounds")
        targeted_resample_seconds.extend(
            (max(0.0, item.start_seconds), max(0.0, min(duration_seconds, item.end_seconds)))
            for item in out_of_bounds
        )

    missing_references = [
        reference.evidence_id
        for claim in claims
        for reference in claim.evidence
        if reference.evidence_id not in evidence_by_id
    ]
    if missing_references:
        failed_gates.append("referenced_evidence_exists")

    has_supported_claims = bool(claims) and all(
        all(reference.evidence_id in evidence_by_id for reference in claim.evidence)
        for claim in claims
    )
    if not has_supported_claims:
        failed_gates.append("claims_supported")

    if result is not None:
        if not result.summary.strip():
            failed_gates.append("schema_valid")
        section_values = result.required_sections
    else:
        section_values = {}
    if any(not section_values.get(section, "").strip() for section in required_sections):
        failed_gates.append("required_sections_non_empty")

    deduplicated_gates = tuple(dict.fromkeys(failed_gates))
    return VerificationReport(
        passed=not deduplicated_gates,
        failed_gates=deduplicated_gates,
        targeted_resample_seconds=tuple(dict.fromkeys(targeted_resample_seconds)),
    )
