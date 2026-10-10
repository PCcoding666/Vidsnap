"""RED-first Batch 3B tests: deterministic orchestrator from draft to exporter inputs.

These tests specify the publishing orchestrator contract: resolve draft image ids
in order against captured frame evidence, render dialogue/article/summary texts
deterministically, and delegate to the existing export_deliverables without any
URL, download, provider, CLI, or model configuration. They import
vidsnap.publishing.orchestrator, which does not exist yet.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vidsnap.contracts import Evidence
from vidsnap.publishing.contracts import DeliverableKind, PublishingResult
from vidsnap.publishing.orchestrator import publish_draft
from vidsnap.publishing.task import PublishingDraft

GENERATED_AT = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
TRANSCRIPT = "First spoken line.\nSecond spoken line with trailing space kept. "


def make_frame(tmp_path: Path, name: str, timestamp: float) -> Evidence:
    path = tmp_path / "media" / f"{name}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8fake-frame-" + name.encode("utf-8"))
    return Evidence(
        id=f"frame-{name}",
        start_seconds=timestamp,
        end_seconds=timestamp,
        modality="frame",
        artifact_path=path,
    )


def draft_article(image_ids: tuple[str, ...]) -> str:
    parts = ["The article body."]
    for evidence_id in image_ids:
        parts.append(f"before-{evidence_id} [[image:{evidence_id}]] after-{evidence_id}")
    return "\n\n".join(parts)


def build_inputs(tmp_path: Path, *, evidence: tuple[Evidence, ...], image_ids: tuple[str, ...]):
    repository_root = tmp_path / "repo"
    repository_root.mkdir(exist_ok=True)
    output_dir = tmp_path / "outside" / "publish"
    draft = PublishingDraft(
        article=draft_article(image_ids),
        summary="The summary body.",
        image_evidence_ids=image_ids,
    )
    return {
        "repository_root": repository_root,
        "output_dir": output_dir,
        "run_id": "run-3b",
        "generated_at": GENERATED_AT,
        "transcript": TRANSCRIPT,
        "draft": draft,
        "evidence": evidence,
    }


def publish(tmp_path: Path, *, evidence: tuple[Evidence, ...], image_ids: tuple[str, ...]):
    return publish_draft(**build_inputs(tmp_path, evidence=evidence, image_ids=image_ids))


def test_publish_draft_renders_all_three_deliverables(tmp_path) -> None:
    alpha = make_frame(tmp_path, "alpha", 5.0)
    beta = make_frame(tmp_path, "beta", 65.0)
    transcript_item = Evidence(
        id="transcript-001",
        start_seconds=0.0,
        end_seconds=8.0,
        modality="transcript",
        content="must stay private",
    )

    result = publish(
        tmp_path, evidence=(beta, transcript_item, alpha), image_ids=("frame-alpha", "frame-beta")
    )

    assert isinstance(result, PublishingResult)
    assert result.run_id == "run-3b"
    output = tmp_path / "outside" / "publish"

    dialogue = (output / "dialogue.md").read_text(encoding="utf-8")
    assert TRANSCRIPT in dialogue, "transcript body must be byte-for-byte present"

    summary = (output / "summary.md").read_text(encoding="utf-8")
    assert "The summary body." in summary

    article = (output / "article.md").read_text(encoding="utf-8")
    assert "The article body." in article
    alpha_block = "![00:00:05](images/frame-alpha.jpg)"
    beta_block = "![00:01:05](images/frame-beta.jpg)"
    assert f"before-frame-alpha {alpha_block} after-frame-alpha" in article
    assert f"before-frame-beta {beta_block} after-frame-beta" in article
    assert article.index(alpha_block) < article.index(beta_block), "draft selection order"
    assert "[[image:" not in article, "placeholders must be replaced in place"
    assert article.strip().endswith("after-frame-beta"), "no blocks may be appended at the end"
    assert str(alpha.artifact_path) not in article, "no absolute external paths in the article"

    copied_alpha = output / "images" / "frame-alpha.jpg"
    copied_beta = output / "images" / "frame-beta.jpg"
    assert copied_alpha.read_bytes() == alpha.artifact_path.read_bytes()
    assert copied_beta.read_bytes() == beta.artifact_path.read_bytes()


def test_image_blocks_use_hhmmss_timestamps_from_frame_evidence(tmp_path) -> None:
    early = make_frame(tmp_path, "early", 5.9)
    late = make_frame(tmp_path, "late", 3661.0)

    publish(tmp_path, evidence=(late, early), image_ids=("frame-late", "frame-early"))

    article = (tmp_path / "outside" / "publish" / "article.md").read_text(encoding="utf-8")
    assert "before-frame-late ![01:01:01](images/frame-late.jpg)" in article
    assert "before-frame-early ![00:00:05](images/frame-early.jpg)" in article
    assert article.index("![01:01:01]") < article.index("![00:00:05]"), "draft order wins"


def test_result_is_reference_only_with_self_contained_image_hashes(tmp_path) -> None:
    alpha = make_frame(tmp_path, "alpha", 5.0)

    result = publish(tmp_path, evidence=(alpha,), image_ids=("frame-alpha",))

    article_reference = next(
        item for item in result.deliverables if item.kind is DeliverableKind.ARTICLE
    )
    assert len(article_reference.image_references) == 1
    image_reference = article_reference.image_references[0]
    assert image_reference.path == Path("images/frame-alpha.jpg")
    assert not image_reference.path.is_absolute()
    source_bytes = alpha.artifact_path.read_bytes()
    copied = tmp_path / "outside" / "publish" / "images" / "frame-alpha.jpg"
    assert copied.read_bytes() == source_bytes
    assert image_reference.sha256 == hashlib.sha256(source_bytes).hexdigest()
    assert image_reference.byte_count == len(source_bytes)
    assert image_reference.timestamp_seconds == 5.0
    assert {item.kind for item in result.deliverables} == set(DeliverableKind)


def test_blank_transcript_is_rejected_without_any_output(tmp_path) -> None:
    alpha = make_frame(tmp_path, "alpha", 5.0)
    inputs = build_inputs(tmp_path, evidence=(alpha,), image_ids=("frame-alpha",))
    inputs["transcript"] = "   \n\t "

    with pytest.raises(ValueError, match="transcript"):
        publish_draft(**inputs)

    assert not inputs["output_dir"].exists()


@pytest.mark.parametrize(
    "case",
    ["unknown-id", "non-frame", "missing-file", "inside-repo", "no-artifact"],
)
def test_invalid_image_selection_is_rejected_without_any_output(tmp_path, case) -> None:
    alpha = make_frame(tmp_path, "alpha", 5.0)
    transcript_item = Evidence(
        id="transcript-001",
        start_seconds=0.0,
        end_seconds=8.0,
        modality="transcript",
        content="spoken",
    )
    missing_file = make_frame(tmp_path, "ghost", 6.0)
    missing_file.artifact_path.unlink()
    inside_repo = make_frame(tmp_path, "inrepo", 7.0)
    repository_root = tmp_path / "repo"
    smuggled = repository_root / "smuggled.jpg"
    repository_root.mkdir(exist_ok=True)
    smuggled.write_bytes(inside_repo.artifact_path.read_bytes())
    inside_repo = inside_repo.model_copy(update={"artifact_path": smuggled})
    no_artifact = Evidence(id="frame-bare", start_seconds=8.0, end_seconds=8.0, modality="frame")

    evidence = (alpha, transcript_item, missing_file, inside_repo, no_artifact)
    image_ids = {
        "unknown-id": ("frame-alpha", "frame-999"),
        "non-frame": ("transcript-001",),
        "missing-file": ("frame-ghost",),
        "inside-repo": ("frame-inrepo",),
        "no-artifact": ("frame-bare",),
    }[case]
    inputs = build_inputs(tmp_path, evidence=evidence, image_ids=image_ids)

    with pytest.raises(ValueError):
        publish_draft(**inputs)

    assert not inputs["output_dir"].exists()


def test_duplicate_supplied_evidence_ids_are_rejected(tmp_path) -> None:
    alpha = make_frame(tmp_path, "alpha", 5.0)
    duplicate = alpha.model_copy()

    inputs = build_inputs(tmp_path, evidence=(alpha, duplicate), image_ids=("frame-alpha",))

    with pytest.raises(ValueError, match="duplicate"):
        publish_draft(**inputs)

    assert not inputs["output_dir"].exists()
