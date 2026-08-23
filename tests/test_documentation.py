"""Documentation accuracy gates for the plugin-first harness release."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PUBLIC_DOCS = ("README.md", "docs/README.md", "docs/migration-to-harness.md")

_SHARED_STATEMENTS = (
    "trust boundary",
    "the model chooses only allowed tools and receives tool results",
    "transcribe_audio before sample_evidence",
    "summary-only and are never reconstructed",
    "Infrastructure validation is not evidence that Harness beats Direct",
    "no live result claims",
)

_REVIEW_KEYWORDS = ("默认", "可选", "隐私", "许可", "成本", "OCR", "scene")

_PROVIDER_DATA_DISCLOSURES = (
    "本地输入选择与出站模型处理",
    "固定配置的 Qwen 端点",
    "并非所有处理都在本地完成",
    "原始媒体默认不会写入 git，也不会包含在 trace 导出中",
    "提供商的数据留存、区域与隐私条款需要用户自行审阅",
    "插件工具本身不能选择 URL、模型或提供商",
)


def _read(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


def test_review_doc_contains_exact_frozen_tool_and_data_sections() -> None:
    text = _read("docs/default-tools-and-data-review.md")

    assert "当前默认内置工具：transcribe_audio、sample_evidence。" in text
    assert (
        "当前可选数据入口：本地视频、可用本地字幕、外部 benchmark manifest、"
        "RunBundle evidence/trace metadata。"
    ) in text


def test_review_doc_marks_every_proposed_addition_not_enabled() -> None:
    text = _read("docs/default-tools-and-data-review.md")

    marked = [line for line in text.splitlines() if "(not enabled)" in line]
    assert len(marked) >= 2
    assert any("OCR" in line for line in marked)
    assert any("scene" in line.lower() for line in marked)
    assert "本次发布未启用任何新工具或新数据入口。" in text


def test_review_doc_lists_required_review_questions() -> None:
    text = _read("docs/default-tools-and-data-review.md")

    for keyword in _REVIEW_KEYWORDS:
        assert keyword in text, f"review questions must cover: {keyword}"


def test_review_doc_discloses_provider_bound_data_flow() -> None:
    text = _read("docs/default-tools-and-data-review.md")

    for statement in _PROVIDER_DATA_DISCLOSURES:
        assert statement in text, f"review doc must disclose: {statement}"


def test_public_docs_state_required_current_behaviors() -> None:
    for relative in _PUBLIC_DOCS:
        text = _read(relative)
        for statement in _SHARED_STATEMENTS:
            assert statement in text, f"{relative} must state: {statement}"


def test_docs_index_links_the_review_checklist() -> None:
    assert "default-tools-and-data-review.md" in _read("docs/README.md")
