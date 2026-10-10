"""Atomic exporter writing the three publishing deliverables outside the repository."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import Field

from vidsnap.contracts.models import StrictModel
from vidsnap.publishing.contracts import (
    IMAGE_FILENAME_PATTERN,
    ArticleImageReference,
    DeliverableKind,
    DeliverableReference,
    PublishingResult,
)

_FILENAMES: dict[DeliverableKind, str] = {
    DeliverableKind.DIALOGUE: "dialogue.md",
    DeliverableKind.ARTICLE: "article.md",
    DeliverableKind.SUMMARY: "summary.md",
}


class ArticleImageInput(StrictModel):
    """One caller-supplied image anchor: timestamp, existing source path, safe filename."""

    timestamp_seconds: float = Field(ge=0)
    path: Path
    filename: str = Field(pattern=IMAGE_FILENAME_PATTERN, max_length=128)


def export_deliverables(
    *,
    repository_root: Path,
    output_dir: Path,
    dialogue: str,
    article: str,
    summary: str,
    article_images: Sequence[ArticleImageInput] = (),
    run_id: str,
    generated_at: datetime,
) -> PublishingResult:
    """Atomically publish self-contained deliverables strictly outside the repository."""
    repository = repository_root.resolve()
    output = _resolve_outside(output_dir, repository, "output_dir")
    _reject_non_empty(output)
    sources = tuple(_validate_image(image, repository) for image in article_images)
    if len({image.filename for image in article_images}) != len(article_images):
        raise ValueError("article image filenames must be unique")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".vidsnap-publishing-", dir=output.parent))
    try:
        image_references = tuple(_stage_image(image, source, staging) for image, source in sources)
        deliverables: list[DeliverableReference] = []
        for kind, text in (
            (DeliverableKind.DIALOGUE, dialogue),
            (DeliverableKind.ARTICLE, article),
            (DeliverableKind.SUMMARY, summary),
        ):
            data = text.encode("utf-8")
            (staging / _FILENAMES[kind]).write_bytes(data)
            deliverables.append(
                DeliverableReference(
                    kind=kind,
                    path=output / _FILENAMES[kind],
                    sha256=hashlib.sha256(data).hexdigest(),
                    byte_count=len(data),
                    image_references=(image_references if kind is DeliverableKind.ARTICLE else ()),
                )
            )
        result = PublishingResult(
            run_id=run_id,
            generated_at=generated_at,
            deliverables=tuple(deliverables),
        )
        _commit(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)

    return result


def _commit(staging: Path, output: Path) -> None:
    """Publish fully staged files without ever deleting a pre-existing location."""
    if output.exists():
        if any(output.iterdir()):
            raise FileExistsError(f"output directory became non-empty: {output}")
        committed: list[Path] = []
        try:
            for staged in sorted(staging.rglob("*")):
                destination = output / staged.relative_to(staging)
                if staged.is_dir():
                    destination.mkdir()
                    continue
                os.link(staged, destination)
                committed.append(destination)
        except BaseException:
            for path in committed:
                path.unlink(missing_ok=True)
            shutil.rmtree(output / "images", ignore_errors=True)
            raise
    else:
        os.replace(staging, output)


def _resolve_outside(path: Path, repository: Path, label: str) -> Path:
    """Resolve one path and reject it if it is relative or inside the repository."""
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    resolved = path.resolve()
    if resolved == repository or resolved.is_relative_to(repository):
        raise ValueError(f"{label} must be located strictly outside the repository root")
    return resolved


def _reject_non_empty(output: Path) -> None:
    """Refuse to reuse an existing non-empty location, protecting user data."""
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError(f"output directory must be empty or absent: {output}")


def _validate_image(image: ArticleImageInput, repository: Path) -> tuple[ArticleImageInput, Path]:
    """Validate one external image source path before any staging work."""
    resolved = _resolve_outside(image.path, repository, "article image")
    if not resolved.is_file():
        raise ValueError("article image must be an existing regular file")
    return image, resolved


def _stage_image(image: ArticleImageInput, source: Path, staging: Path) -> ArticleImageReference:
    """Copy one validated image into staging/images and hash the copied bytes."""
    data = source.read_bytes()
    images_dir = staging / "images"
    images_dir.mkdir(exist_ok=True)
    (images_dir / image.filename).write_bytes(data)
    return ArticleImageReference(
        timestamp_seconds=image.timestamp_seconds,
        path=Path("images") / image.filename,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_count=len(data),
    )
