"""The eval-set format, the committed suites, and suite validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.eval.helpers import SUITES_DIR, committed_suite, item_payload, make_item, write_suite
from vidsnap.eval.suite import (
    EvalItem,
    load_suite,
    resolve_media,
    resolve_suite_path,
    validate_suite,
)

TASKS = ("t1", "t2a", "t2b", "t3")


@pytest.mark.parametrize("task", TASKS)
def test_committed_suites_load_and_have_no_format_errors(task: str, tmp_path: Path) -> None:
    loaded = committed_suite(task)
    assert loaded.suite.task == task
    assert 5 <= len(loaded.suite.items) <= 10
    issues = validate_suite(loaded, tmp_path / "no-media", check_hashes=False)
    errors = [issue for issue in issues if issue.level == "error"]
    # Only missing public media may be an error when no media is present.
    assert all("media missing" in issue.message for issue in errors), errors


def test_committed_suites_cover_sources_and_owner_slots() -> None:
    kinds = {"synthetic": 0, "public": 0, "owner": 0}
    for task in TASKS:
        for item in committed_suite(task).suite.items:
            kinds[item.source.kind] += 1
            if item.source.kind == "owner":
                assert item.status == "placeholder"
                assert item.notes and "sha256" in item.notes
            if item.source.kind != "owner":
                assert item.source.licence
    assert kinds["owner"] == 5
    assert kinds["synthetic"] >= 10
    assert kinds["public"] >= 3


def test_synthetic_reference_transcript_derives_from_the_spec() -> None:
    loaded = committed_suite("t3")
    item = next(item for item in loaded.suite.items if item.item_id == "t3-syn-01")
    spec = loaded.specs["t3-syn-01"]
    transcript = item.reference.transcript
    assert transcript is not None and transcript.from_generator
    assert [segment.text for segment in transcript.segments] == [
        slide.narration for slide in spec.slides
    ]
    ends = [segment.end_seconds for segment in transcript.segments]
    assert ends[-1] == pytest.approx(spec.duration_seconds())
    starts = [segment.start_seconds for segment in transcript.segments]
    assert starts[1:] == pytest.approx(ends[:-1])
    for question in item.reference.questions:
        assert 0 <= question.window[0] < question.window[1] <= spec.duration_seconds()


def test_t3_reference_questions_and_no_private_data() -> None:
    for item in committed_suite("t3").suite.items:
        if item.status == "placeholder":
            assert item.notes is not None and "PRIVACY" in item.notes
            continue
        assert len(item.reference.questions) >= 2
        assert item.source.kind == "synthetic"


def test_paths_must_stay_relative() -> None:
    for bad in ("../outside.mp4", "/abs/path.mp4"):
        payload = item_payload()
        payload["source"]["path"] = bad
        with pytest.raises(ValidationError):
            EvalItem.model_validate(payload)


def test_keyword_groups_must_be_non_empty() -> None:
    payload = item_payload()
    payload["reference"]["key_points"][0]["match"] = [[]]
    with pytest.raises(ValidationError):
        EvalItem.model_validate(payload)


def test_duplicate_item_ids_are_refused(tmp_path: Path) -> None:
    path = write_suite(tmp_path / "t1.json", "t1", [item_payload(), item_payload()])
    with pytest.raises(ValueError, match="invalid"):
        load_suite(path)


def test_validation_flags_reference_and_task_rules(tmp_path: Path) -> None:
    no_reference = item_payload(item_id="x-02")
    no_reference["reference"] = {}
    long_clip = item_payload(item_id="x-03")
    long_clip["source"]["duration_seconds"] = 300.0
    path = write_suite(tmp_path / "t2b.json", "t2b", [no_reference, long_clip])
    issues = validate_suite(load_suite(path), None)
    messages = {(issue.item_id, issue.message) for issue in issues if issue.level == "error"}
    assert ("x-02", "ready items need key points or questions") in messages
    assert ("x-03", "t2b clips must be at most 120 s") in messages


def test_public_media_hash_mismatch_is_an_error(tmp_path: Path) -> None:
    media = tmp_path / "media"
    (media / "public").mkdir(parents=True)
    (media / "public" / "x.mp4").write_bytes(b"not the registered bytes")
    path = write_suite(tmp_path / "t1.json", "t1", [item_payload()])
    issues = validate_suite(load_suite(path), media)
    assert any(issue.message == "media SHA-256 does not match the manifest" for issue in issues)


def test_suite_names_resolve_to_files() -> None:
    assert resolve_suite_path("t1", SUITES_DIR) == SUITES_DIR / "t1.json"
    assert resolve_media(make_item(), Path("/m")) == Path("/m/public/x.mp4")


def test_committed_suites_are_valid_json_with_sorted_schema() -> None:
    for task in TASKS:
        data = json.loads((SUITES_DIR / f"{task}.json").read_text(encoding="utf-8"))
        assert data["schema_version"] == "vidsnap.eval-suite/v1"
