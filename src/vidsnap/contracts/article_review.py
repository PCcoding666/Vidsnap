"""Versioned, strict editorial review records (no provider or recipe dependencies)."""

from typing import Literal

from pydantic import Field

from vidsnap.contracts.models import StrictModel


class FigureReview(StrictModel):
    section_index: int = Field(ge=0)
    figure_index: int = Field(ge=0)
    evidence_id: str | None
    verdict: Literal["supported", "contradicted", "insufficient"]
    reason: str = Field(min_length=1, max_length=1000)


class EditorialIssue(StrictModel):
    # None identifies the title, introduction, takeaways or summary as a group.
    section_index: int | None = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class ArticleReview(StrictModel):
    schema_version: Literal["vidsnap.article-review/v1"] = "vidsnap.article-review/v1"
    figures: list[FigureReview] = Field(max_length=96)
    issues: list[EditorialIssue] = Field(max_length=32)
