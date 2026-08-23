"""Evidence-grounding verifier behavior."""

from vidsnap.contracts import Claim, Evidence, EvidenceReference, VideoAnalysisResult
from vidsnap.loop.verifier import verify_claims


def test_verifier_rejects_missing_evidence_and_out_of_bounds_timestamps() -> None:
    report = verify_claims(
        claims=[
            Claim(
                text="A workflow is demonstrated.",
                evidence=[
                    EvidenceReference(evidence_id="missing"),
                    EvidenceReference(evidence_id="late-frame"),
                ],
            )
        ],
        evidence=[
            Evidence(id="late-frame", start_seconds=0, end_seconds=2, modality="frame"),
        ],
        duration_seconds=1,
    )

    assert report.passed is False
    assert "referenced_evidence_exists" in report.failed_gates
    assert "timestamps_in_bounds" in report.failed_gates


def test_verifier_marks_empty_claim_output_as_incomplete_not_verified() -> None:
    report = verify_claims(claims=[], evidence=[], duration_seconds=1)

    assert report.passed is False
    assert "claims_are_supported" in report.failed_gates


def test_verifier_rejects_an_empty_required_result_section() -> None:
    report = verify_claims(
        claims=[],
        evidence=[],
        duration_seconds=1,
        result=VideoAnalysisResult(
            summary="A summary without a required section.",
            required_sections={"risks": ""},
        ),
        required_sections=("risks",),
    )

    assert report.passed is False
    assert "required_sections_covered" in report.failed_gates
