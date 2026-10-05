import pytest
from pydantic import ValidationError

from vidsnap.contracts import Evidence, VideoGoal
from vidsnap.recipes import InterviewRecipeTaskAdapter
from vidsnap.recipes.interview import (
    BriefPoint,
    CommentaryArticleBlock,
    EditorialStatus,
    InterviewRecipeResult,
    SourceArticleBlock,
    TranscriptSegment,
)
from vidsnap.tasks.base import TaskVerification
from vidsnap.video.probe import MediaProbe


@pytest.fixture()
def interview_result() -> InterviewRecipeResult:
    seg_q = TranscriptSegment(
        id="seg-q",
        kind="question",
        speaker="Host",
        start_time=1,
        end_time=3,
        source_text="What changed?",
        rendered_text="What changed?",
        source_language="en",
        rendered_language="en",
        transcript_evidence_id="ev-q",
        frame_evidence_id="ev-frame",
        editorial_status="source",
    )
    seg_a = TranscriptSegment(
        id="seg-a",
        kind="answer",
        speaker="Guest",
        start_time=4,
        end_time=8,
        source_text="The workflow became auditable.",
        rendered_text="The workflow became auditable.",
        source_language="en",
        rendered_language="en",
        transcript_evidence_id="ev-a",
        frame_evidence_id=None,
        editorial_status="source",
    )
    block_q = SourceArticleBlock(id="block-q", type="source", segment_id="seg-q")
    block_a = SourceArticleBlock(id="block-a", type="source", segment_id="seg-a")
    block_c = CommentaryArticleBlock(
        id="block-c",
        type="commentary",
        text="The guest said the workflow became auditable.",
        evidence_ids=["ev-a"],
        editorial_status="model_commentary",
    )
    brief = BriefPoint(
        id="brief-1",
        commentary="The workflow became auditable.",
        evidence=["ev-a"],
        editorial_status="model_commentary",
    )
    return InterviewRecipeResult(
        segments=[seg_q, seg_a],
        blocks=[block_q, block_a, block_c],
        brief_points=[brief],
    )


@pytest.fixture()
def interview_evidence() -> list[Evidence]:
    return [
        Evidence(
            id="ev-q",
            start_seconds=1,
            end_seconds=3,
            modality="transcript",
            content="Host: What changed?",
        ),
        Evidence(
            id="ev-a",
            start_seconds=4,
            end_seconds=8,
            modality="transcript",
            content="Guest: The workflow became auditable.",
        ),
        Evidence(
            id="ev-frame",
            start_seconds=1,
            end_seconds=3,
            modality="frame",
            content="host asking question",
        ),
    ]


@pytest.fixture()
def media_probe() -> MediaProbe:
    return MediaProbe(
        duration_seconds=10,
        fps=30,
        width=1920,
        height=1080,
        has_audio=True,
    )


@pytest.fixture()
def adapter() -> InterviewRecipeTaskAdapter:
    return InterviewRecipeTaskAdapter(goal=VideoGoal(objective="Preserve interview"))


def test_output_model_is_interview_recipe_result(adapter: InterviewRecipeTaskAdapter) -> None:
    assert adapter.output_model is InterviewRecipeResult


def test_parse_final_accepts_fixture_payload_and_rejects_unknown_field(
    interview_result: InterviewRecipeResult,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    payload = interview_result.model_dump(mode="json")

    parsed = adapter.parse_final(payload)
    assert isinstance(parsed, InterviewRecipeResult)

    with pytest.raises(ValidationError):
        adapter.parse_final({**payload, "unexpected_field": "nope"})


def test_verify_passes_all_six_gates(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    verification = adapter.verify(interview_result, interview_evidence, media_probe)

    assert isinstance(verification, TaskVerification)
    assert verification.passed is True
    assert verification.gates == {
        "dialogue_present": True,
        "dialogue_retained": True,
        "timestamps_in_bounds": True,
        "referenced_evidence_exists": True,
        "source_text_supported": True,
        "provenance_complete": True,
    }


def test_missing_question_segment_fails_dialogue_present(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    segments = [item for item in interview_result.segments if item.kind != "question"]
    modified = interview_result.model_copy(update={"segments": segments})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["dialogue_present"] is False


def test_missing_answer_segment_fails_dialogue_present(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    segments = [item for item in interview_result.segments if item.kind != "answer"]
    modified = interview_result.model_copy(update={"segments": segments})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["dialogue_present"] is False


def test_missing_question_source_block_fails_dialogue_retained(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    blocks = [item for item in interview_result.blocks if item.id != "block-q"]
    modified = interview_result.model_copy(update={"blocks": blocks})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["dialogue_retained"] is False


def test_missing_answer_source_block_fails_dialogue_retained(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    blocks = [item for item in interview_result.blocks if item.id != "block-a"]
    modified = interview_result.model_copy(update={"blocks": blocks})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["dialogue_retained"] is False


def test_missing_question_transcript_evidence_fails_referenced_evidence_exists(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    evidence = [item for item in interview_evidence if item.id != "ev-q"]

    verification = adapter.verify(interview_result, evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["referenced_evidence_exists"] is False


def test_question_transcript_evidence_with_frame_modality_fails_referenced_evidence_exists(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    evidence = [
        item.model_copy(update={"modality": "frame"}) if item.id == "ev-q" else item
        for item in interview_evidence
    ]

    verification = adapter.verify(interview_result, evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["referenced_evidence_exists"] is False


def test_missing_frame_evidence_fails_referenced_evidence_exists(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    evidence = [item for item in interview_evidence if item.id != "ev-frame"]

    verification = adapter.verify(interview_result, evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["referenced_evidence_exists"] is False


def test_answer_end_time_beyond_duration_fails_timestamps_in_bounds(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    segments = [
        item.model_copy(update={"end_time": 12.0}) if item.id == "seg-a" else item
        for item in interview_result.segments
    ]
    modified = interview_result.model_copy(update={"segments": segments})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["timestamps_in_bounds"] is False


def test_unsupported_answer_evidence_content_fails_source_text_supported(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    evidence = [
        item.model_copy(update={"content": "unrelated text"}) if item.id == "ev-a" else item
        for item in interview_evidence
    ]

    verification = adapter.verify(interview_result, evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["source_text_supported"] is False


def test_commentary_block_with_unknown_evidence_fails_referenced_evidence_exists(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    blocks = [
        item.model_copy(update={"evidence_ids": ["ev-a", "missing-commentary"]})
        if isinstance(item, CommentaryArticleBlock)
        else item
        for item in interview_result.blocks
    ]
    modified = interview_result.model_copy(update={"blocks": blocks})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["referenced_evidence_exists"] is False


def test_brief_point_with_unknown_evidence_fails_referenced_evidence_exists(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    brief_points = [
        item.model_copy(update={"evidence": ["ev-a", "missing-brief"]})
        for item in interview_result.brief_points
    ]
    modified = interview_result.model_copy(update={"brief_points": brief_points})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["referenced_evidence_exists"] is False


def test_invented_answer_speaker_fails_source_text_supported(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    segments = [
        item.model_copy(update={"speaker": "Invented Speaker"}) if item.id == "seg-a" else item
        for item in interview_result.segments
    ]
    modified = interview_result.model_copy(update={"segments": segments})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["source_text_supported"] is False


def test_answer_time_outside_referenced_evidence_fails_timestamps_in_bounds(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
) -> None:
    segments = [
        item.model_copy(update={"start_time": 3.5, "end_time": 8.5}) if item.id == "seg-a" else item
        for item in interview_result.segments
    ]
    modified = interview_result.model_copy(update={"segments": segments})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["timestamps_in_bounds"] is False


@pytest.mark.parametrize(
    "status",
    [EditorialStatus.unknown, EditorialStatus.unverified, EditorialStatus.partial],
)
def test_unverified_editorial_status_fails_provenance_complete(
    interview_result: InterviewRecipeResult,
    interview_evidence: list[Evidence],
    media_probe: MediaProbe,
    adapter: InterviewRecipeTaskAdapter,
    status: EditorialStatus,
) -> None:
    segments = [
        item.model_copy(update={"editorial_status": status}) if item.id == "seg-a" else item
        for item in interview_result.segments
    ]
    modified = interview_result.model_copy(update={"segments": segments})

    verification = adapter.verify(modified, interview_evidence, media_probe)

    assert verification.passed is False
    assert verification.gates["provenance_complete"] is False
