"""Failing-first tests for the reference-only publishing deliverable contracts."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from vidsnap.publishing.contracts import (
    ArticleImageReference,
    DeliverableKind,
    DeliverableReference,
    PublishingResult,
)

_SHA256 = "a" * 64
_RUN_ID = "11111111-2222-3333-4444-555555555555"


def _image(**overrides: object) -> ArticleImageReference:
    defaults: dict[str, object] = {
        "timestamp_seconds": 42.5,
        "path": Path("images/frame-001.jpg"),
        "sha256": _SHA256,
        "byte_count": 2048,
    }
    defaults.update(overrides)
    return ArticleImageReference(**defaults)  # type: ignore[arg-type]


def _deliverable(kind: DeliverableKind, **overrides: object) -> DeliverableReference:
    defaults: dict[str, object] = {
        "kind": kind,
        "path": Path(f"/tmp/vidsnap-out/{kind.value}.md"),
        "sha256": _SHA256,
        "byte_count": 1024,
    }
    defaults.update(overrides)
    return DeliverableReference(**defaults)  # type: ignore[arg-type]


def _result(**overrides: object) -> PublishingResult:
    defaults: dict[str, object] = {
        "run_id": _RUN_ID,
        "generated_at": datetime(2026, 8, 24, 0, 0, 0, tzinfo=timezone.utc),
        "deliverables": (
            _deliverable(DeliverableKind.DIALOGUE),
            _deliverable(
                DeliverableKind.ARTICLE,
                image_references=(_image(),),
            ),
            _deliverable(DeliverableKind.SUMMARY),
        ),
    }
    defaults.update(overrides)
    return PublishingResult(**defaults)  # type: ignore[arg-type]


def test_valid_publishing_result_parses() -> None:
    result = _result()
    kinds = {item.kind for item in result.deliverables}
    assert kinds == {
        DeliverableKind.DIALOGUE,
        DeliverableKind.ARTICLE,
        DeliverableKind.SUMMARY,
    }
    article = next(item for item in result.deliverables if item.kind is DeliverableKind.ARTICLE)
    assert article.image_references[0].timestamp_seconds == 42.5


def test_result_carries_no_deliverable_content() -> None:
    assert not {
        "transcript",
        "dialogue_text",
        "article_text",
        "summary_text",
        "model_response",
    } & set(PublishingResult.model_fields)


def test_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _result(surprise="x")


def test_deliverable_reference_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _deliverable(DeliverableKind.SUMMARY, surprise="x")


def test_image_reference_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _image(surprise="x")


def test_kind_must_be_one_of_the_three_deliverables() -> None:
    with pytest.raises(ValidationError):
        DeliverableReference(
            kind="video",  # type: ignore[arg-type]
            path=Path("/tmp/x.md"),
            sha256=_SHA256,
            byte_count=1,
        )


@pytest.mark.parametrize("bad_hash", ["a" * 63, "A" * 64, "g" * 64])
def test_deliverable_sha256_must_be_64_lowercase_hex(bad_hash: str) -> None:
    with pytest.raises(ValidationError):
        _deliverable(DeliverableKind.DIALOGUE, sha256=bad_hash)


@pytest.mark.parametrize("bad_hash", ["a" * 63, "A" * 64, "g" * 64])
def test_image_sha256_must_be_64_lowercase_hex(bad_hash: str) -> None:
    with pytest.raises(ValidationError):
        _image(sha256=bad_hash)


def test_image_timestamp_must_not_be_negative() -> None:
    with pytest.raises(ValidationError):
        _image(timestamp_seconds=-0.1)


def test_image_path_must_be_relative_and_inside_images() -> None:
    with pytest.raises(ValidationError):
        _image(path=Path("/tmp/vidsnap-out/images/frame-001.jpg"))
    with pytest.raises(ValidationError):
        _image(path=Path("frame-001.jpg"))
    assert _image(path=Path("images/frame-002.png")).path == Path("images/frame-002.png")


@pytest.mark.parametrize(
    "bad_path",
    [
        Path("images/.."),
        Path("images/."),
        Path("images/a/b.jpg"),
        Path("images/no-extension"),
        Path("images/.hidden.jpg"),
        Path("images/x.jpg/../y.jpg"),
        Path("images/..jpg"),
    ],
)
def test_image_path_component_must_be_one_safe_filename(bad_path: Path) -> None:
    with pytest.raises(ValidationError):
        _image(path=bad_path)


def test_image_byte_count_must_not_be_negative() -> None:
    with pytest.raises(ValidationError):
        _image(byte_count=-1)


def test_byte_count_must_not_be_negative() -> None:
    with pytest.raises(ValidationError):
        _deliverable(DeliverableKind.SUMMARY, byte_count=-1)


def test_duplicate_deliverable_kinds_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _result(
            deliverables=(
                _deliverable(DeliverableKind.DIALOGUE),
                _deliverable(DeliverableKind.DIALOGUE),
                _deliverable(DeliverableKind.SUMMARY),
            )
        )


def test_every_deliverable_kind_is_required() -> None:
    with pytest.raises(ValidationError):
        _result(
            deliverables=(
                _deliverable(DeliverableKind.DIALOGUE),
                _deliverable(DeliverableKind.ARTICLE),
            )
        )


def test_image_references_are_rejected_on_dialogue() -> None:
    with pytest.raises(ValidationError):
        _deliverable(DeliverableKind.DIALOGUE, image_references=(_image(),))


def test_image_references_are_rejected_on_summary() -> None:
    with pytest.raises(ValidationError):
        _deliverable(DeliverableKind.SUMMARY, image_references=(_image(),))


def test_generated_at_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        _result(generated_at=datetime(2026, 8, 24, 0, 0, 0))


def test_generated_at_rejects_non_utc_timezone() -> None:
    with pytest.raises(ValidationError):
        _result(generated_at=datetime(2026, 8, 24, 0, 0, 0, tzinfo=timezone(timedelta(hours=2))))


def test_run_id_must_be_present() -> None:
    with pytest.raises(ValidationError):
        _result(run_id="")
