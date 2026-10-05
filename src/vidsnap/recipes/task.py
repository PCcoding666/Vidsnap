"""Deterministic task adapter for the interview recipe's grounded output."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import JsonValue

from vidsnap.contracts import Evidence, VideoGoal
from vidsnap.recipes.interview import (
    CommentaryArticleBlock,
    EditorialStatus,
    InterviewRecipeResult,
    SourceArticleBlock,
)
from vidsnap.tasks.base import TaskVerification
from vidsnap.video.probe import MediaProbe

_UNVERIFIED_STATUSES = frozenset(
    {EditorialStatus.unknown, EditorialStatus.unverified, EditorialStatus.partial}
)
_DIALOGUE_KINDS = frozenset({"question", "answer"})


_ASCII_COLON = ":"
_FULLWIDTH_COLON = "："


def _normalize(text: str) -> str:
    """Collapse whitespace runs and drop case before containment checks."""
    return " ".join(text.split()).casefold()


def _dialogue_present(output: InterviewRecipeResult) -> bool:
    kinds = {segment.kind for segment in output.segments}
    return "question" in kinds and "answer" in kinds


def _dialogue_retained(output: InterviewRecipeResult) -> bool:
    referenced = {
        block.segment_id for block in output.blocks if isinstance(block, SourceArticleBlock)
    }
    return all(
        segment.id in referenced for segment in output.segments if segment.kind in _DIALOGUE_KINDS
    )


def _timestamps_in_bounds(
    output: InterviewRecipeResult,
    evidence: Sequence[Evidence],
    probe: MediaProbe,
) -> bool:
    """Require every segment inside the video duration and its transcript evidence span."""
    span_by_id = {
        item.id: (item.start_seconds, item.end_seconds)
        for item in evidence
        if item.modality == "transcript"
    }
    for segment in output.segments:
        if not 0 <= segment.start_time < segment.end_time <= probe.duration_seconds:
            return False
        span = span_by_id.get(segment.transcript_evidence_id)
        if span is None:
            return False
        evidence_start, evidence_end = span
        if segment.start_time < evidence_start or segment.end_time > evidence_end:
            return False
    return True


def _referenced_evidence_exists(
    output: InterviewRecipeResult,
    evidence: Sequence[Evidence],
) -> bool:
    transcript_ids = {item.id for item in evidence if item.modality == "transcript"}
    frame_ids = {item.id for item in evidence if item.modality == "frame"}
    known_ids = {item.id for item in evidence}
    for segment in output.segments:
        if segment.transcript_evidence_id not in transcript_ids:
            return False
        if segment.frame_evidence_id is not None and segment.frame_evidence_id not in frame_ids:
            return False
    for block in output.blocks:
        if isinstance(block, CommentaryArticleBlock) and any(
            evidence_id not in known_ids for evidence_id in block.evidence_ids
        ):
            return False
    for point in output.brief_points:
        if any(evidence_id not in known_ids for evidence_id in point.evidence):
            return False
    return True


def _speaker_label_present(content: str, speaker: str) -> bool:
    """Require an explicit 'Speaker:' line label; never a substring match."""
    label = _normalize(speaker)
    if not label:
        return False
    for raw_line in content.splitlines():
        line = _normalize(raw_line)
        if not line.startswith(label):
            continue
        remainder = line[len(label) :]
        if remainder.startswith((_ASCII_COLON, _FULLWIDTH_COLON)):
            return True
        if remainder[:1].isspace() and remainder.lstrip().startswith(
            (_ASCII_COLON, _FULLWIDTH_COLON)
        ):
            return True
    return False


def _source_text_supported(
    output: InterviewRecipeResult,
    evidence: Sequence[Evidence],
) -> bool:
    content_by_id = {item.id: item.content for item in evidence if item.modality == "transcript"}
    for segment in output.segments:
        content = content_by_id.get(segment.transcript_evidence_id)
        if content is None:
            return False
        if _normalize(segment.source_text) not in _normalize(content):
            return False
        if not _speaker_label_present(content, segment.speaker):
            return False
    return True


def _provenance_complete(output: InterviewRecipeResult) -> bool:
    return all(segment.editorial_status not in _UNVERIFIED_STATUSES for segment in output.segments)


class InterviewRecipeTaskAdapter:
    """Parse and verify interview recipe output without any model calls."""

    output_model: type[InterviewRecipeResult] = InterviewRecipeResult

    def __init__(self, goal: VideoGoal) -> None:
        self.goal = goal

    def parse_final(self, payload: dict[str, JsonValue]) -> InterviewRecipeResult:
        """Accept only the strict InterviewRecipeResult schema."""
        return InterviewRecipeResult.model_validate(payload)

    def verify(
        self,
        output: InterviewRecipeResult,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> TaskVerification:
        """Check dialogue retention, grounding, and provenance deterministically."""
        gates = {
            "dialogue_present": _dialogue_present(output),
            "dialogue_retained": _dialogue_retained(output),
            "timestamps_in_bounds": _timestamps_in_bounds(output, evidence, probe),
            "referenced_evidence_exists": _referenced_evidence_exists(output, evidence),
            "source_text_supported": _source_text_supported(output, evidence),
            "provenance_complete": _provenance_complete(output),
        }
        return TaskVerification(passed=all(gates.values()), gates=gates)
