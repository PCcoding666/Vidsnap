"""Failing-first tests for the out-of-repository publishing deliverable exporter."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from vidsnap.publishing.contracts import DeliverableKind, PublishingResult
from vidsnap.publishing.exporter import ArticleImageInput, export_deliverables

_GENERATED_AT = datetime(2026, 8, 24, 0, 0, 0, tzinfo=timezone.utc)
_RUN_ID = "11111111-2222-3333-4444-555555555555"
_DIALOGUE = "完整对话稿\n嘉宾：你好，世界。"
_ARTICLE = "图文笔记正文"
_SUMMARY = "短摘要：一段话。"
_IMAGE_BYTES = b"\xff\xd8\xff\xe0real-image-bytes"


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir(exist_ok=True)
    return repository


def _export(tmp_path: Path, **overrides: object) -> PublishingResult:
    defaults: dict[str, object] = {
        "repository_root": _repository(tmp_path),
        "output_dir": tmp_path / "out" / "video-001",
        "dialogue": _DIALOGUE,
        "article": _ARTICLE,
        "summary": _SUMMARY,
        "article_images": (),
        "run_id": _RUN_ID,
        "generated_at": _GENERATED_AT,
    }
    defaults.update(overrides)
    return export_deliverables(**defaults)  # type: ignore[arg-type]


def _deliverable(result: PublishingResult, kind: DeliverableKind):
    return next(item for item in result.deliverables if item.kind is kind)


def _image(tmp_path: Path) -> Path:
    media = tmp_path / "media"
    media.mkdir(exist_ok=True)
    image = media / "frame-001.jpg"
    image.write_bytes(_IMAGE_BYTES)
    return image


def test_success_writes_three_fixed_markdown_files(tmp_path: Path) -> None:
    result = _export(tmp_path)
    output_dir = tmp_path / "out" / "video-001"
    assert (output_dir / "dialogue.md").read_text(encoding="utf-8") == _DIALOGUE
    assert (output_dir / "article.md").read_text(encoding="utf-8") == _ARTICLE
    assert (output_dir / "summary.md").read_text(encoding="utf-8") == _SUMMARY
    assert result.run_id == _RUN_ID
    assert result.generated_at == _GENERATED_AT
    assert (
        _deliverable(result, DeliverableKind.DIALOGUE).path
        == (output_dir / "dialogue.md").resolve()
    )


def test_chinese_utf8_byte_count_and_hash_are_real(tmp_path: Path) -> None:
    result = _export(tmp_path)
    expected = _DIALOGUE.encode("utf-8")
    dialogue = _deliverable(result, DeliverableKind.DIALOGUE)
    assert dialogue.byte_count == len(expected)
    assert dialogue.byte_count > len(_DIALOGUE)
    assert dialogue.sha256 == hashlib.sha256(expected).hexdigest()


def test_returned_json_contains_no_deliverable_text(tmp_path: Path) -> None:
    result = _export(tmp_path)
    payload = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    for fragment in ("嘉宾：你好，世界。", "图文笔记正文", "短摘要：一段话。"):
        assert fragment not in payload


def test_output_dir_inside_repository_is_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    with pytest.raises(ValueError):
        _export(tmp_path, repository_root=repository, output_dir=repository / "out")
    assert not (repository / "out").exists()


def test_relative_output_dir_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _export(tmp_path, output_dir=Path("relative/out"))


def test_symlinked_output_dir_escaping_into_repository_is_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    inner = repository / "inner"
    inner.mkdir()
    link = tmp_path / "link"
    link.symlink_to(inner)
    with pytest.raises(ValueError):
        _export(tmp_path, repository_root=repository, output_dir=link)


def test_existing_non_empty_output_dir_is_rejected(tmp_path: Path) -> None:
    output_dir = tmp_path / "out" / "video-001"
    output_dir.mkdir(parents=True)
    user_file = output_dir / "user-data.txt"
    user_file.write_text("keep me", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _export(tmp_path, output_dir=output_dir)
    assert user_file.read_text(encoding="utf-8") == "keep me"


def test_existing_empty_output_dir_is_accepted(tmp_path: Path) -> None:
    output_dir = tmp_path / "out" / "video-001"
    output_dir.mkdir(parents=True)
    result = _export(tmp_path, output_dir=output_dir)
    assert (output_dir / "dialogue.md").is_file()
    assert _deliverable(result, DeliverableKind.DIALOGUE).byte_count > 0


def test_missing_image_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "media" / "missing.jpg"
    with pytest.raises(ValueError):
        _export(
            tmp_path,
            article_images=(
                ArticleImageInput(timestamp_seconds=1.0, path=missing, filename="missing.jpg"),
            ),
        )


def test_image_directory_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "media"
    directory.mkdir()
    with pytest.raises(ValueError):
        _export(
            tmp_path,
            article_images=(
                ArticleImageInput(timestamp_seconds=1.0, path=directory, filename="media.jpg"),
            ),
        )


def test_relative_image_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _export(
            tmp_path,
            article_images=(
                ArticleImageInput(
                    timestamp_seconds=1.0, path=Path("media/x.jpg"), filename="x.jpg"
                ),
            ),
        )


def test_image_inside_repository_is_rejected(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    inside = repository / "frame.jpg"
    inside.write_bytes(_IMAGE_BYTES)
    with pytest.raises(ValueError):
        _export(
            tmp_path,
            repository_root=repository,
            article_images=(
                ArticleImageInput(timestamp_seconds=1.0, path=inside, filename="frame.jpg"),
            ),
        )


def test_negative_image_timestamp_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ArticleImageInput(timestamp_seconds=-0.1, path=_image(tmp_path), filename="frame-001.jpg")


@pytest.mark.parametrize(
    "unsafe_filename",
    ["../escape.jpg", "nested/dir.jpg", ".hidden.jpg", "frame.jpg/..", "no-extension", ""],
)
def test_unsafe_image_filenames_are_rejected(tmp_path: Path, unsafe_filename: str) -> None:
    with pytest.raises(ValidationError):
        ArticleImageInput(timestamp_seconds=1.0, path=_image(tmp_path), filename=unsafe_filename)


def test_image_is_copied_with_real_hash_bytes_and_relative_reference(tmp_path: Path) -> None:
    image = _image(tmp_path)
    result = _export(
        tmp_path,
        article_images=(
            ArticleImageInput(timestamp_seconds=42.5, path=image, filename="frame-001.jpg"),
        ),
    )
    article = _deliverable(result, DeliverableKind.ARTICLE)
    assert len(article.image_references) == 1
    reference = article.image_references[0]
    assert reference.timestamp_seconds == 42.5
    assert reference.path == Path("images/frame-001.jpg")
    assert not reference.path.is_absolute()
    assert reference.sha256 == hashlib.sha256(_IMAGE_BYTES).hexdigest()
    assert reference.byte_count == len(_IMAGE_BYTES)
    assert image.read_bytes() == _IMAGE_BYTES

    output_dir = tmp_path / "out" / "video-001"
    copied = output_dir / "images" / "frame-001.jpg"
    assert copied.is_file()
    assert copied.read_bytes() == _IMAGE_BYTES


def test_duplicate_image_filenames_are_rejected(tmp_path: Path) -> None:
    image = _image(tmp_path)
    with pytest.raises(ValueError):
        _export(
            tmp_path,
            article_images=(
                ArticleImageInput(timestamp_seconds=1.0, path=image, filename="frame-001.jpg"),
                ArticleImageInput(timestamp_seconds=2.0, path=image, filename="frame-001.jpg"),
            ),
        )


def test_image_read_failure_rolls_back_everything(tmp_path: Path) -> None:
    """A filesystem failure while copying one image leaves no committed output."""
    good = _image(tmp_path)
    unreadable = tmp_path / "media" / "locked.jpg"
    unreadable.write_bytes(_IMAGE_BYTES)
    unreadable.chmod(0)
    output_parent = tmp_path / "out"
    try:
        with pytest.raises(OSError):
            _export(
                tmp_path,
                article_images=(
                    ArticleImageInput(timestamp_seconds=1.0, path=good, filename="good.jpg"),
                    ArticleImageInput(
                        timestamp_seconds=2.0, path=unreadable, filename="locked.jpg"
                    ),
                ),
            )
        assert not (output_parent / "video-001").exists()
        assert set(output_parent.iterdir()) == set()
    finally:
        unreadable.chmod(0o600)


def test_non_utc_generated_at_is_rejected_before_commit(tmp_path: Path) -> None:
    output_dir = tmp_path / "out" / "video-001"
    with pytest.raises(ValidationError):
        _export(tmp_path, generated_at=datetime(2026, 8, 24, 8, 0, 0))
    assert not output_dir.exists()


def test_failure_midway_leaves_no_partial_output(tmp_path: Path) -> None:
    """A failure while encoding the real UTF-8 bytes leaves no committed output.

    The exporter contract requires every hash and byte_count to come from the
    actual encoded UTF-8 bytes, so a text whose encode() fails aborts the run;
    the observable guarantee is that nothing appears at or beside output_dir
    except what existed before the call.
    """

    class BrokenText(str):
        def encode(self, encoding: str = "utf-8", errors: str = "strict") -> bytes:
            raise RuntimeError("simulated write failure")

    output_parent = tmp_path / "out"
    output_parent.mkdir()
    marker = output_parent / "keep-me.txt"
    marker.write_text("pre-existing", encoding="utf-8")
    with pytest.raises(RuntimeError):
        _export(tmp_path, summary=BrokenText(_SUMMARY))
    assert not (output_parent / "video-001").exists()
    assert set(output_parent.iterdir()) == {marker}
