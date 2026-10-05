import pytest
from pydantic import ValidationError

from vidsnap.recipes.interview import (
    BriefPoint,
    CommentaryArticleBlock,
    EditorialStatus,
    InterviewRecipeResult,
    SourceArticleBlock,
    TranscriptSegment,
)

EDITORIAL_STATUS_VALUES = {
    "source",
    "faithful_translation",
    "edited_for_clarity",
    "model_commentary",
    "unknown",
    "unverified",
    "partial",
}

SEGMENT_KINDS = ("question", "answer", "context")


def segment_payload(**overrides):
    payload = {
        "id": "seg-1",
        "kind": "answer",
        "speaker": "Engineer",
        "start_time": 0.0,
        "end_time": 12.5,
        "source_text": "We shipped the migration in three stages.",
        "rendered_text": "We shipped the migration in three stages.",
        "source_language": "en",
        "rendered_language": "en",
        "transcript_evidence_id": "ev-1",
        "editorial_status": EditorialStatus.source,
    }
    payload.update(overrides)
    return payload


def test_editorial_status_has_exactly_seven_values():
    assert len(EditorialStatus) == 7
    assert {status.value for status in EditorialStatus} == EDITORIAL_STATUS_VALUES


@pytest.mark.parametrize("kind", SEGMENT_KINDS)
def test_segment_accepts_valid_payload(kind):
    segment = TranscriptSegment(**segment_payload(kind=kind))
    assert segment.id == "seg-1"
    assert segment.kind == kind
    assert segment.speaker == "Engineer"
    assert segment.editorial_status == EditorialStatus.source
    assert segment.frame_evidence_id is None


def test_segment_accepts_optional_frame_evidence_id():
    segment = TranscriptSegment(**segment_payload(frame_evidence_id="fr-1"))
    assert segment.frame_evidence_id == "fr-1"


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize(
    "field",
    [
        "id",
        "kind",
        "speaker",
        "source_text",
        "rendered_text",
        "source_language",
        "rendered_language",
        "transcript_evidence_id",
    ],
)
def test_segment_required_strings_are_nonblank(field, blank):
    with pytest.raises(ValidationError):
        TranscriptSegment(**segment_payload(**{field: blank}))


@pytest.mark.parametrize(
    ("start_time", "end_time"),
    [(12.5, 12.5), (12.5, 0.0)],
)
def test_segment_end_time_must_exceed_start_time(start_time, end_time):
    with pytest.raises(ValidationError):
        TranscriptSegment(**segment_payload(start_time=start_time, end_time=end_time))


def test_segment_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        TranscriptSegment(**segment_payload(kind="narration"))


def test_segment_rejects_model_commentary_status():
    with pytest.raises(ValidationError):
        TranscriptSegment(**segment_payload(editorial_status=EditorialStatus.model_commentary))


def test_source_status_forbids_rendered_text_mutation():
    with pytest.raises(ValidationError):
        TranscriptSegment(**segment_payload(rendered_text="We shipped it in stages."))


def test_source_status_forbids_rendered_language_mutation():
    with pytest.raises(ValidationError):
        TranscriptSegment(**segment_payload(rendered_language="es"))


def test_different_languages_accept_faithful_translation():
    segment = TranscriptSegment(
        **segment_payload(
            rendered_text="Enviamos la migración en tres etapas.",
            rendered_language="es",
            editorial_status=EditorialStatus.faithful_translation,
        )
    )
    assert segment.rendered_language == "es"


@pytest.mark.parametrize(
    "status",
    [
        EditorialStatus.source,
        EditorialStatus.edited_for_clarity,
        EditorialStatus.unknown,
        EditorialStatus.unverified,
        EditorialStatus.partial,
    ],
)
def test_different_languages_require_faithful_translation(status):
    with pytest.raises(ValidationError):
        TranscriptSegment(
            **segment_payload(
                rendered_text="Enviamos la migración en tres etapas.",
                rendered_language="es",
                editorial_status=status,
            )
        )


def test_same_language_changed_text_accepts_edited_for_clarity():
    segment = TranscriptSegment(
        **segment_payload(
            source_text="We we shipped the migration in three stages.",
            rendered_text="We shipped the migration in three stages.",
            editorial_status=EditorialStatus.edited_for_clarity,
        )
    )
    assert segment.editorial_status == EditorialStatus.edited_for_clarity


def test_edited_for_clarity_rejects_newly_invented_words():
    with pytest.raises(ValidationError):
        TranscriptSegment(
            **segment_payload(
                source_text="We shipped the migration in three stages.",
                rendered_text="We cancelled the migration for legal reasons.",
                editorial_status=EditorialStatus.edited_for_clarity,
            )
        )


def test_edited_for_clarity_rejects_punctuation_only_rendered_text():
    with pytest.raises(ValidationError):
        TranscriptSegment(
            **segment_payload(
                source_text="We shipped the migration in three stages.",
                rendered_text="!! ??? ...",
                editorial_status=EditorialStatus.edited_for_clarity,
            )
        )


def test_edited_for_clarity_rejects_invented_arabic_words():
    with pytest.raises(ValidationError):
        TranscriptSegment(
            **segment_payload(
                source_text="شحنّا المشروع اليوم",
                rendered_text="ألغينا المشروع اليوم",
                editorial_status=EditorialStatus.edited_for_clarity,
            )
        )


def test_edited_for_clarity_accepts_removal_only_arabic():
    segment = TranscriptSegment(
        **segment_payload(
            source_text="شحنّا المشروع اليوم",
            rendered_text="شحنّا المشروع",
            editorial_status=EditorialStatus.edited_for_clarity,
        )
    )
    assert segment.rendered_text == "شحنّا المشروع"


def test_source_block_is_strict_source_reference():
    block = SourceArticleBlock(id="blk-1", type="source", segment_id="seg-1")
    assert block.type == "source"
    assert block.segment_id == "seg-1"


def test_source_block_rejects_other_types_and_extra_payloads():
    with pytest.raises(ValidationError):
        SourceArticleBlock(id="blk-1", type="commentary", segment_id="seg-1")
    with pytest.raises(ValidationError):
        SourceArticleBlock(id="blk-1", type="source", segment_id="seg-1", text="unexpected")


def test_commentary_block_requires_text_evidence_and_model_commentary():
    block = CommentaryArticleBlock(
        id="blk-2",
        type="commentary",
        text="The rollout actually happened in two waves.",
        evidence_ids=["ev-1"],
        editorial_status=EditorialStatus.model_commentary,
    )
    assert block.type == "commentary"
    assert block.editorial_status == EditorialStatus.model_commentary


def test_commentary_block_rejects_other_types_and_bad_payloads():
    with pytest.raises(ValidationError):
        CommentaryArticleBlock(
            id="blk-2",
            type="source",
            text="wrong type",
            evidence_ids=["ev-1"],
            editorial_status=EditorialStatus.model_commentary,
        )
    with pytest.raises(ValidationError):
        CommentaryArticleBlock(
            id="blk-2",
            type="commentary",
            text="no evidence",
            evidence_ids=[],
            editorial_status=EditorialStatus.model_commentary,
        )
    with pytest.raises(ValidationError):
        CommentaryArticleBlock(
            id="blk-2",
            type="commentary",
            text="wrong status",
            evidence_ids=["ev-1"],
            editorial_status=EditorialStatus.edited_for_clarity,
        )


def test_brief_point_requires_commentary_and_evidence():
    point = BriefPoint(
        id="pt-1",
        commentary="The migration shipped in three stages.",
        evidence=["ev-1"],
        editorial_status=EditorialStatus.model_commentary,
    )
    assert point.commentary == "The migration shipped in three stages."
    assert point.evidence == ["ev-1"]


def test_brief_point_rejects_missing_evidence_and_wrong_status():
    with pytest.raises(ValidationError):
        BriefPoint(
            id="pt-1",
            commentary="Unsupported claim.",
            evidence=[],
            editorial_status=EditorialStatus.model_commentary,
        )
    with pytest.raises(ValidationError):
        BriefPoint(
            id="pt-1",
            commentary="Wrong status.",
            evidence=["ev-1"],
            editorial_status=EditorialStatus.source,
        )


def test_result_resolves_source_segment_references():
    segment = TranscriptSegment(**segment_payload())
    result = InterviewRecipeResult(
        segments=[segment],
        blocks=[SourceArticleBlock(id="blk-1", type="source", segment_id="seg-1")],
        brief_points=[],
    )
    assert result.blocks[0].segment_id == "seg-1"


def test_result_rejects_unresolved_source_segment_reference():
    segment = TranscriptSegment(**segment_payload())
    with pytest.raises(ValidationError):
        InterviewRecipeResult(
            segments=[segment],
            blocks=[SourceArticleBlock(id="blk-1", type="source", segment_id="seg-missing")],
            brief_points=[],
        )


def test_result_rejects_duplicate_segment_ids():
    segment = TranscriptSegment(**segment_payload())
    with pytest.raises(ValidationError):
        InterviewRecipeResult(
            segments=[segment, TranscriptSegment(**segment_payload())],
            blocks=[SourceArticleBlock(id="blk-1", type="source", segment_id="seg-1")],
            brief_points=[],
        )


def test_result_rejects_duplicate_block_ids_across_types():
    segment = TranscriptSegment(**segment_payload())
    with pytest.raises(ValidationError):
        InterviewRecipeResult(
            segments=[segment],
            blocks=[
                SourceArticleBlock(id="blk-1", type="source", segment_id="seg-1"),
                CommentaryArticleBlock(
                    id="blk-1",
                    type="commentary",
                    text="The rollout shipped in three stages.",
                    evidence_ids=["ev-1"],
                    editorial_status=EditorialStatus.model_commentary,
                ),
            ],
            brief_points=[],
        )


def test_result_rejects_duplicate_brief_point_ids():
    segment = TranscriptSegment(**segment_payload())

    def point() -> BriefPoint:
        return BriefPoint(
            id="pt-1",
            commentary="The migration shipped in three stages.",
            evidence=["ev-1"],
            editorial_status=EditorialStatus.model_commentary,
        )

    with pytest.raises(ValidationError):
        InterviewRecipeResult(
            segments=[segment],
            blocks=[SourceArticleBlock(id="blk-1", type="source", segment_id="seg-1")],
            brief_points=[point(), point()],
        )
