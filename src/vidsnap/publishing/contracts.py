"""Strict reference-only contracts for out-of-repository publishing deliverables."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import Field, model_validator
from typing_extensions import Self

from vidsnap.contracts.models import StrictModel

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
IMAGE_FILENAME_PATTERN = r"^[A-Za-z0-9_-]+\.[A-Za-z0-9]+$"


class DeliverableKind(str, Enum):
    """The three finished deliverables produced for one published video."""

    DIALOGUE = "dialogue"
    ARTICLE = "article"
    SUMMARY = "summary"


class ArticleImageReference(StrictModel):
    """One copied image embedded in the article, addressed relative to output_dir."""

    timestamp_seconds: float = Field(ge=0)
    path: Path
    sha256: str = Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN)
    byte_count: int = Field(ge=0)

    @model_validator(mode="after")
    def path_is_self_contained(self) -> Self:
        parts = self.path.parts
        if self.path.is_absolute() or parts[:1] != ("images",) or len(parts) != 2:
            raise ValueError("image path must be a relative images/<filename> reference")
        if not re.fullmatch(IMAGE_FILENAME_PATTERN, parts[1]):
            raise ValueError("image filename must be one safe name with an extension")
        return self


class DeliverableReference(StrictModel):
    """A content-free reference to one deliverable kept outside the repository."""

    kind: DeliverableKind
    path: Path
    sha256: str = Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN)
    byte_count: int = Field(ge=0)
    image_references: tuple[ArticleImageReference, ...] = ()

    @model_validator(mode="after")
    def images_only_for_articles(self) -> Self:
        if self.image_references and self.kind is not DeliverableKind.ARTICLE:
            raise ValueError("image references are only allowed on the article deliverable")
        return self


class PublishingResult(StrictModel):
    """Audit metadata plus exactly one reference per required deliverable kind."""

    run_id: str = Field(min_length=1, max_length=128)
    generated_at: datetime
    deliverables: tuple[DeliverableReference, ...]

    @model_validator(mode="after")
    def validate_deliverables_and_timestamp(self) -> Self:
        kinds = tuple(item.kind for item in self.deliverables)
        if len(kinds) != len(set(kinds)):
            raise ValueError("duplicate deliverable kinds are not allowed")
        missing = {kind for kind in DeliverableKind} - set(kinds)
        if missing:
            names = ", ".join(sorted(kind.value for kind in missing))
            raise ValueError(f"missing required deliverable kinds: {names}")
        offset = self.generated_at.utcoffset()
        if self.generated_at.tzinfo is None or offset is None:
            raise ValueError("generated_at must include a UTC timezone")
        if offset.total_seconds() != 0:
            raise ValueError("generated_at must be expressed in UTC")
        return self
