"""Deterministic orchestrator mapping a verified draft onto exporter inputs."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from vidsnap.contracts import Evidence
from vidsnap.publishing.contracts import PublishingResult
from vidsnap.publishing.exporter import ArticleImageInput, export_deliverables
from vidsnap.publishing.task import IMAGE_PLACEHOLDER_PATTERN, PublishingDraft

_DIALOGUE_HEADING = "# Dialogue"


def publish_draft(
    *,
    repository_root: Path,
    output_dir: Path,
    run_id: str,
    generated_at: datetime,
    transcript: str,
    draft: PublishingDraft,
    evidence: Sequence[Evidence],
) -> PublishingResult:
    """Publish one verified draft via the exporter; validate everything first."""
    if not transcript.strip():
        raise ValueError("transcript must be non-blank")
    repository = repository_root.resolve()
    selected = _select_images(draft, evidence, repository)
    dialogue = f"{_DIALOGUE_HEADING}\n\n{transcript}"
    article = _render_article(draft, selected)
    images = [
        ArticleImageInput(
            timestamp_seconds=item.start_seconds, path=resolved, filename=_image_filename(item)
        )
        for item, resolved in selected
    ]
    return export_deliverables(
        repository_root=repository_root,
        output_dir=output_dir,
        dialogue=dialogue,
        article=article,
        summary=draft.summary,
        article_images=images,
        run_id=run_id,
        generated_at=generated_at,
    )


def _select_images(
    draft: PublishingDraft,
    evidence: Sequence[Evidence],
    repository: Path,
) -> list[tuple[Evidence, Path]]:
    """Resolve draft image ids in order; reject anything ambiguous or internal."""
    by_id: dict[str, Evidence] = {}
    for item in evidence:
        if item.id in by_id:
            raise ValueError(f"duplicate evidence ids supplied: {item.id}")
        by_id[item.id] = item

    selected: list[tuple[Evidence, Path]] = []
    for evidence_id in draft.image_evidence_ids:
        candidate = by_id.get(evidence_id)
        if candidate is None:
            raise ValueError(f"unknown image evidence id: {evidence_id}")
        if candidate.modality != "frame":
            raise ValueError(f"image evidence must be a frame: {evidence_id}")
        if candidate.artifact_path is None:
            raise ValueError(f"frame evidence has no artifact path: {evidence_id}")
        if not candidate.artifact_path.is_file():
            raise ValueError(f"frame evidence artifact is missing: {evidence_id}")
        resolved = candidate.artifact_path.resolve()
        if resolved == repository or resolved.is_relative_to(repository):
            raise ValueError(
                f"frame evidence artifact must be outside the repository: {evidence_id}"
            )
        selected.append((candidate, resolved))
    return selected


def _render_article(draft: PublishingDraft, selected: Sequence[tuple[Evidence, Path]]) -> str:
    """Replace each inline placeholder with one Markdown image block in place."""
    by_id = {item.id: item for item, _resolved in selected}

    def replace(match: re.Match[str]) -> str:
        item = by_id[match.group(1)]
        return f"![{_timestamp_label(item.start_seconds)}](images/{_image_filename(item)})"

    return IMAGE_PLACEHOLDER_PATTERN.sub(replace, draft.article)


def _image_filename(item: Evidence) -> str:
    """Derive one deterministic, exporter-safe filename from kernel-allocated evidence."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", item.id):
        raise ValueError(f"image evidence id is not a safe filename stem: {item.id}")
    suffix = item.artifact_path.suffix.lower() if item.artifact_path is not None else ""
    if not re.fullmatch(r"\.[A-Za-z0-9]+", suffix):
        raise ValueError(f"image evidence artifact has an unsafe suffix: {item.id}")
    return f"{item.id}{suffix}"


def _timestamp_label(seconds: float) -> str:
    """Format one non-negative timestamp as HH:MM:SS without rounding up."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
