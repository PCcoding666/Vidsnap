from pathlib import Path

import pytest

from vidsnap.recipes import InterviewRecipeArtifacts, render_interview_recipe
from vidsnap.recipes.interview import (
    BriefPoint,
    CommentaryArticleBlock,
    EditorialStatus,
    InterviewRecipeResult,
    SourceArticleBlock,
    TranscriptSegment,
)

TRACE_BYTES = b"<html><body>offline trace</body></html>"
EXPECTED_FILES = {"transcript.zh.md", "interview.article.md", "brief.md", "trace.html"}


def _result() -> InterviewRecipeResult:
    return InterviewRecipeResult(
        segments=[
            TranscriptSegment(
                id="seg-1",
                kind="question",
                speaker="Host",
                start_time=0.0,
                end_time=4.5,
                source_text="欢迎收看本期节目",
                rendered_text="欢迎收看本期节目",
                source_language="zh",
                rendered_language="zh",
                transcript_evidence_id="e01",
                frame_evidence_id=None,
                editorial_status=EditorialStatus.source,
            ),
            TranscriptSegment(
                id="seg-2",
                kind="answer",
                speaker="Guest",
                start_time=4.5,
                end_time=9.0,
                source_text="我觉得这个功能非常有用",
                rendered_text="I think this feature is very useful",
                source_language="zh",
                rendered_language="en",
                transcript_evidence_id="e02",
                frame_evidence_id="f01",
                editorial_status=EditorialStatus.faithful_translation,
            ),
            TranscriptSegment(
                id="seg-3",
                kind="context",
                speaker="Host",
                start_time=9.0,
                end_time=12.0,
                source_text="那个那个我们接着看下一个话题",
                rendered_text="我们接着看下一个话题",
                source_language="zh",
                rendered_language="zh",
                transcript_evidence_id="e03",
                frame_evidence_id=None,
                editorial_status=EditorialStatus.edited_for_clarity,
            ),
        ],
        blocks=[
            SourceArticleBlock(id="block-1", type="source", segment_id="seg-1"),
            SourceArticleBlock(id="block-2", type="source", segment_id="seg-2"),
            CommentaryArticleBlock(
                id="block-3",
                type="commentary",
                text="The answer highlights the usefulness of the feature.",
                evidence_ids=["e02", "f01"],
                editorial_status=EditorialStatus.model_commentary,
            ),
        ],
        brief_points=[
            BriefPoint(
                id="point-1",
                commentary="The interview confirms the feature is useful.",
                evidence=["e02", "f01"],
                editorial_status=EditorialStatus.model_commentary,
            ),
        ],
    )


def _render(out: Path) -> InterviewRecipeArtifacts:
    return render_interview_recipe(_result(), out, TRACE_BYTES)


def test_interview_recipe_artifacts_annotations() -> None:
    assert callable(render_interview_recipe)
    annotations = InterviewRecipeArtifacts.__annotations__
    assert "transcript_path" in annotations
    assert "article_path" in annotations
    assert "brief_path" in annotations
    assert "trace_path" in annotations


def test_render_writes_exactly_the_four_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "out"
    artifacts = _render(out)
    assert artifacts.transcript_path == out / "transcript.zh.md"
    assert artifacts.article_path == out / "interview.article.md"
    assert artifacts.brief_path == out / "brief.md"
    assert artifacts.trace_path == out / "trace.html"
    assert {entry.name for entry in out.iterdir()} == EXPECTED_FILES
    assert (out / "trace.html").read_bytes() == TRACE_BYTES


def test_transcript_contract(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _render(out)
    text = (out / "transcript.zh.md").read_text(encoding="utf-8")
    rendered = [
        "欢迎收看本期节目",
        "I think this feature is very useful",
        "我们接着看下一个话题",
    ]
    positions = [text.index(fragment) for fragment in rendered]
    assert positions == sorted(positions)
    for speaker in ("Host", "Guest"):
        assert speaker in text
    for label in ("Question", "Answer", "Context"):
        assert label in text
    for stamp in ("00:00:00", "00:00:04", "00:00:09"):
        assert stamp in text
    for status in ("source", "faithful_translation", "edited_for_clarity"):
        assert status in text
    for segment_id in ("seg-1", "seg-2", "seg-3"):
        assert segment_id in text
    for evidence_id in ("e01", "e02", "e03"):
        assert evidence_id in text
    assert "f01" in text
    lowered = text.lower()
    assert "summary" not in lowered
    assert "摘要" not in text


def test_article_contract(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _render(out)
    text = (out / "interview.article.md").read_text(encoding="utf-8")
    assert "欢迎收看本期节目" in text
    assert "I think this feature is very useful" in text
    assert "Host" in text
    assert "Guest" in text
    assert "00:00:00" in text
    assert "00:00:04" in text
    paragraphs = [p for p in text.split("\n\n") if "Model commentary" in p]
    assert len(paragraphs) == 1
    paragraph = paragraphs[0]
    assert "The answer highlights the usefulness of the feature." in paragraph
    assert "e02" in paragraph
    assert "f01" in paragraph
    assert "Host" not in paragraph
    assert "Guest" not in paragraph


def test_brief_contract(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _render(out)
    text = (out / "brief.md").read_text(encoding="utf-8")
    assert "Brief" in text or "Executive Summary" in text
    assert "secondary" in text.lower()
    assert "The interview confirms the feature is useful." in text
    assert "e02" in text
    assert "f01" in text


def test_two_renders_are_byte_identical(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    _render(first)
    _render(second)
    for name in sorted(EXPECTED_FILES):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_refuses_non_empty_output_directory(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _render(out)
    transcript = out / "transcript.zh.md"
    transcript.write_bytes(b"sentinel")
    with pytest.raises(ValueError):
        _render(out)
    assert transcript.read_bytes() == b"sentinel"


def test_render_is_atomic_when_trace_write_fails(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_bytes(b"untouched")
    original_write_bytes = Path.write_bytes

    def failing_write_bytes(self: Path, data) -> int:
        if self.name == "trace.html":
            raise OSError("simulated late trace write failure")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write_bytes)

    with pytest.raises(OSError):
        _render(out)

    assert not out.exists() or not any(out.iterdir())
    assert sentinel.read_bytes() == b"untouched"
