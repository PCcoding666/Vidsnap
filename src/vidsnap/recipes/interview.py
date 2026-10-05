"""Strict data models for the interview recipe's grounded editorial output."""

from __future__ import annotations

import unicodedata
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from vidsnap.contracts.models import StrictModel

_CJK_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0x3040, 0x30FF),
    (0xAC00, 0xD7AF),
)


def _is_cjk_character(character: str) -> bool:
    code_point = ord(character)
    return any(start <= code_point <= end for start, end in _CJK_RANGES)


def _editorial_tokens(text: str) -> tuple[str, ...]:
    """Tokenize generically: CJK characters individually, other alphanumerics as words.

    Combining marks attach to the current word; punctuation and whitespace
    delimit words. Tokens are casefolded, giving a stable stream for
    removal-only subsequence checks without any language-specific lists.
    """
    tokens: list[str] = []
    current: list[str] = []
    for character in text:
        if character.isspace() or unicodedata.category(character).startswith("P"):
            if current:
                tokens.append("".join(current).casefold())
                current = []
            continue
        if unicodedata.category(character).startswith("M"):
            if current:
                current.append(character)
            continue
        if _is_cjk_character(character):
            if current:
                tokens.append("".join(current).casefold())
                current = []
            tokens.append(character)
            continue
        if unicodedata.category(character).startswith(("N", "L")):
            current.append(character)
            continue
        if current:
            tokens.append("".join(current).casefold())
            current = []
    if current:
        tokens.append("".join(current).casefold())
    return tuple(tokens)


def _is_removal_only_edit(source: str, rendered: str) -> bool:
    """Check rendered is source with tokens removed, order preserved."""
    source_tokens = _editorial_tokens(source)
    rendered_tokens = _editorial_tokens(rendered)
    if not rendered_tokens or len(rendered_tokens) > len(source_tokens):
        return False
    index = 0
    for token in rendered_tokens:
        while index < len(source_tokens) and source_tokens[index] != token:
            index += 1
        if index >= len(source_tokens):
            return False
        index += 1
    return True


class EditorialStatus(str, Enum):
    """Truthful provenance of one rendered editorial fragment."""

    source = "source"
    faithful_translation = "faithful_translation"
    edited_for_clarity = "edited_for_clarity"
    model_commentary = "model_commentary"
    unknown = "unknown"
    unverified = "unverified"
    partial = "partial"


class TranscriptSegment(StrictModel):
    """One grounded transcript span that may be rendered verbatim or translated."""

    id: str = Field(min_length=1, max_length=256)
    kind: Literal["question", "answer", "context"]
    speaker: str = Field(min_length=1, max_length=256)
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    source_text: str = Field(min_length=1, max_length=100_000)
    rendered_text: str = Field(min_length=1, max_length=100_000)
    source_language: str = Field(min_length=1, max_length=32)
    rendered_language: str = Field(min_length=1, max_length=32)
    transcript_evidence_id: str = Field(min_length=1, max_length=256)
    frame_evidence_id: str | None = Field(default=None, min_length=1, max_length=256)
    editorial_status: EditorialStatus

    @model_validator(mode="after")
    def validate_time_range(self) -> TranscriptSegment:
        """Require a non-empty time window for every segment."""
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")
        return self

    @model_validator(mode="after")
    def validate_rendering_integrity(self) -> TranscriptSegment:
        """Keep rendered text truthful relative to its declared editorial status."""
        if self.editorial_status is EditorialStatus.model_commentary:
            raise ValueError("transcript segments cannot carry model_commentary status")
        if self.editorial_status is EditorialStatus.source:
            if self.rendered_text != self.source_text:
                raise ValueError("source status requires rendered_text to match source_text")
            if self.rendered_language != self.source_language:
                raise ValueError(
                    "source status requires rendered_language to match source_language"
                )
        elif self.editorial_status is EditorialStatus.edited_for_clarity:
            if not _is_removal_only_edit(self.source_text, self.rendered_text):
                raise ValueError(
                    "edited_for_clarity rendered_text may only remove tokens from source_text"
                )
        elif (
            self.rendered_language != self.source_language
            and self.editorial_status is not EditorialStatus.faithful_translation
        ):
            raise ValueError("rendered_language may differ only under faithful_translation status")
        return self


class SourceArticleBlock(StrictModel):
    """An article block that renders exactly one existing transcript segment."""

    id: str = Field(min_length=1, max_length=256)
    type: Literal["source"]
    segment_id: str = Field(min_length=1, max_length=256)


class CommentaryArticleBlock(StrictModel):
    """An article block carrying model commentary backed by explicit evidence."""

    id: str = Field(min_length=1, max_length=256)
    type: Literal["commentary"]
    text: str = Field(min_length=1, max_length=100_000)
    evidence_ids: list[str] = Field(min_length=1)
    editorial_status: Literal[EditorialStatus.model_commentary]


class BriefPoint(StrictModel):
    """One takeaway bullet whose claim is backed by explicit evidence."""

    id: str = Field(min_length=1, max_length=256)
    commentary: str = Field(min_length=1, max_length=100_000)
    evidence: list[str] = Field(min_length=1)
    editorial_status: Literal[EditorialStatus.model_commentary]


class InterviewRecipeResult(StrictModel):
    """Structured interview recipe output with resolvable block references."""

    segments: list[TranscriptSegment] = Field(default_factory=list)
    blocks: list[SourceArticleBlock | CommentaryArticleBlock] = Field(default_factory=list)
    brief_points: list[BriefPoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_block_references(self) -> InterviewRecipeResult:
        """Require unique ids and resolvable source block references."""
        segment_ids: set[str] = set()
        for segment in self.segments:
            if segment.id in segment_ids:
                raise ValueError("segments contain duplicate ids")
            segment_ids.add(segment.id)
        block_ids: set[str] = set()
        for block in self.blocks:
            if block.id in block_ids:
                raise ValueError("blocks contain duplicate ids")
            block_ids.add(block.id)
            if isinstance(block, SourceArticleBlock) and block.segment_id not in segment_ids:
                raise ValueError(
                    f"source block {block.id!r} references unknown segment {block.segment_id!r}"
                )
        brief_ids: set[str] = set()
        for point in self.brief_points:
            if point.id in brief_ids:
                raise ValueError("brief points contain duplicate ids")
            brief_ids.add(point.id)
        return self
