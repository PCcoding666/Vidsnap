"""Deterministic Markdown rendering of grounded interview recipe outputs."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from vidsnap.recipes.interview import (
    InterviewRecipeResult,
    SourceArticleBlock,
    TranscriptSegment,
)


@dataclass(frozen=True)
class InterviewRecipeArtifacts:
    transcript_path: Path
    article_path: Path
    brief_path: Path
    trace_path: Path


def _timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _span(segment: TranscriptSegment) -> str:
    return f"{_timestamp(segment.start_time)} - {_timestamp(segment.end_time)}"


def _render_transcript(result: InterviewRecipeResult) -> str:
    parts = ["# Interview transcript"]
    for segment in result.segments:
        lines = [
            f"## {segment.id} · {segment.kind.capitalize()} · {segment.speaker}",
            "",
            f"- Time: {_span(segment)}",
            f"- Editorial status: {segment.editorial_status.value}",
            f"- Transcript evidence: {segment.transcript_evidence_id}",
        ]
        if segment.frame_evidence_id is not None:
            lines.append(f"- Frame evidence: {segment.frame_evidence_id}")
        lines.extend(
            [
                f"- Languages: {segment.source_language} -> {segment.rendered_language}",
                f"- Text: {segment.rendered_text}",
            ]
        )
        parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


def _render_article(result: InterviewRecipeResult) -> str:
    segments = {segment.id: segment for segment in result.segments}
    parts = ["# Interview article"]
    for block in result.blocks:
        if isinstance(block, SourceArticleBlock):
            segment = segments[block.segment_id]
            evidence = segment.transcript_evidence_id
            if segment.frame_evidence_id is not None:
                evidence = f"{evidence} · {segment.frame_evidence_id}"
            lines = [
                f"### {segment.id} · {segment.speaker} · {_span(segment)}",
                "",
                segment.rendered_text,
                "",
                f"Editorial status: {segment.editorial_status.value} · Evidence: {evidence}",
            ]
            parts.append("\n".join(lines))
        else:
            evidence = ", ".join(block.evidence_ids)
            parts.append(f"Model commentary: {block.text} Evidence: {evidence}")
    return "\n\n".join(parts) + "\n"


def _render_brief(result: InterviewRecipeResult) -> str:
    parts = ["# Brief", "Secondary editorial compression of the interview article."]
    for point in result.brief_points:
        evidence = ", ".join(point.evidence)
        parts.append(f"- {point.commentary} Evidence: {evidence}")
    return "\n\n".join(parts) + "\n"


def render_interview_recipe(
    result: InterviewRecipeResult,
    output_dir: Path,
    payload: bytes,
) -> InterviewRecipeArtifacts:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"refusing non-empty output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        transcript_path = staging / "transcript.zh.md"
        article_path = staging / "interview.article.md"
        brief_path = staging / "brief.md"
        trace_path = staging / "trace.html"
        transcript_path.write_text(_render_transcript(result), encoding="utf-8")
        article_path.write_text(_render_article(result), encoding="utf-8")
        brief_path.write_text(_render_brief(result), encoding="utf-8")
        trace_path.write_bytes(payload)
        if output_dir.exists():
            output_dir.rmdir()
        os.rename(staging, output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return InterviewRecipeArtifacts(
        transcript_path=output_dir / "transcript.zh.md",
        article_path=output_dir / "interview.article.md",
        brief_path=output_dir / "brief.md",
        trace_path=output_dir / "trace.html",
    )
