"""The local cross-run index: one JSON line per finished run, plus human reviews.

Summaries are derived only from a finalized RunBundle, so bundles written by
v0.1.0 and the packaged demo fixture summarize too, with nulls where those
bundles recorded nothing.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest
from legacy_bundles import V010_RUN_ID, write_v010_failed_bundle
from pydantic import ValidationError

from vidsnap.trace.run_index import (
    INDEX_FILE_NAME,
    RunReview,
    append_index_record,
    latest_reviews,
    read_index,
    resolve_run_id,
    review_record,
    summarize_run,
)


def _demo_bundle(tmp_path: Path) -> Path:
    target = tmp_path / "demo-run"
    source = resources.files("vidsnap.demo") / "fixtures" / "run"

    def copy(node: object, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for entry in node.iterdir():  # type: ignore[attr-defined]
            if entry.is_dir():
                copy(entry, destination / entry.name)
            else:
                (destination / entry.name).write_bytes(entry.read_bytes())

    copy(source, target)
    return target


def test_v010_bundle_summarizes_with_nulls_for_what_it_never_recorded(tmp_path: Path) -> None:
    bundle = write_v010_failed_bundle(tmp_path / "v010")

    record = summarize_run(bundle, command="analyze")

    assert record["schema_version"] == "vidsnap.run-index/v1"
    assert record["record"] == "run"
    assert record["run_id"] == V010_RUN_ID
    assert record["started_at"] == "2026-10-05T00:00:00Z"
    assert record["finalized_at"] == "2026-10-05T00:00:11Z"
    assert record["command"] == "analyze"
    assert record["package_version"] == "0.1.0"
    assert record["policy"] == "FixedPolicy"
    assert record["terminal_state"] == "FAILED"
    assert record["duration_ms"] == 690
    # Never recorded by v0.1.0: stays null rather than guessed.
    assert record["goal"] is None
    assert record["input_sha256"] is None
    assert record["input_size_bytes"] is None
    assert record["provider"] is None
    assert record["model"] is None
    assert record["recipe"] is None
    assert record["failure_category"] is None
    assert record["http_status"] is None
    # Recorded by v0.1.0 in other places: recovered from there.
    assert record["input_duration_seconds"] == 42.5
    assert record["failure_reason"] == "unexpected kernel error"
    assert record["model_calls"] == 1
    assert record["tool_calls"] == 1
    assert record["failed_gates"] is None
    # The failed request reported nothing: tokens are not complete, cost not computable.
    assert record["input_tokens"] == 0
    assert record["output_tokens"] == 0
    assert record["tokens_reported"] is False
    assert record["cost"] is None
    assert record["bundle_path"] == str(bundle.resolve())


def test_v010_manifest_provider_identity_is_used_when_present(tmp_path: Path) -> None:
    bundle = write_v010_failed_bundle(tmp_path / "v010", provider_identity=True)

    record = summarize_run(bundle, command="analyze")

    assert (record["provider"], record["model"]) == ("acme", "acme-large")


def test_packaged_demo_fixture_summarizes(tmp_path: Path) -> None:
    record = summarize_run(_demo_bundle(tmp_path), command="demo")

    assert record["run_id"] == "00000000-0000-4000-8000-000000000001"
    assert record["terminal_state"] == "SUCCEEDED"
    assert record["goal"] == "Summarize a synthetic 20-second demo clip with grounded observations"
    assert record["failed_gates"] == []
    assert record["duration_ms"] == 5700
    # The synthetic demo records zeroed, unreported usage: never treated as measured.
    assert record["tokens_reported"] is False
    assert record["model_calls"] is None


def test_summary_refuses_a_directory_without_a_manifest(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    with pytest.raises(ValueError):
        summarize_run(tmp_path / "empty", command="analyze")


def test_records_append_one_line_each_and_read_back_in_order(tmp_path: Path) -> None:
    runs_root = tmp_path / "nested" / "runs"
    first = summarize_run(write_v010_failed_bundle(tmp_path / "a"), command="analyze")
    second = dict(first, run_id="second-run")

    index_path = append_index_record(runs_root, first)
    append_index_record(runs_root, second)

    assert index_path == runs_root / INDEX_FILE_NAME
    lines = index_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["run_id"] for line in lines] == [V010_RUN_ID, "second-run"]
    contents = read_index(runs_root)
    assert [record["run_id"] for record in contents.records] == [V010_RUN_ID, "second-run"]
    assert contents.invalid_lines == 0


def test_reading_skips_and_counts_lines_it_cannot_parse(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    (runs_root / INDEX_FILE_NAME).write_text(
        '{"schema_version": "vidsnap.run-index/v1", "record": "run", "run_id": "ok"}\n'
        "not json\n"
        '{"schema_version": "other/v9", "record": "run", "run_id": "foreign"}\n'
        "\n",
        encoding="utf-8",
    )

    contents = read_index(runs_root)

    assert [record["run_id"] for record in contents.records] == ["ok"]
    assert contents.invalid_lines == 2


def test_missing_index_reads_as_empty(tmp_path: Path) -> None:
    contents = read_index(tmp_path / "never-created")

    assert contents.records == []
    assert contents.invalid_lines == 0
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"edit_minutes": -1},
        {"factual_errors": -1},
        {"images_replaced": 1.5},
        {"note": "x" * 4001},
        {"published": True, "unexpected": 1},
    ],
)
def test_reviews_reject_empty_negative_or_unknown_fields(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RunReview.model_validate(fields)


def test_review_record_keeps_unrecorded_fields_null() -> None:
    record = review_record("run-1", RunReview(edit_minutes=12.5, published=True))

    assert record["schema_version"] == "vidsnap.run-index/v1"
    assert record["record"] == "review"
    assert record["run_id"] == "run-1"
    assert isinstance(record["reviewed_at"], str)
    assert record["edit_minutes"] == 12.5
    assert record["published"] is True
    assert record["factual_errors"] is None
    assert record["images_replaced"] is None
    assert record["note"] is None


def test_latest_review_per_run_wins() -> None:
    records = [
        {"record": "run", "run_id": "a"},
        review_record("a", RunReview(edit_minutes=5)),
        review_record("a", RunReview(edit_minutes=7, factual_errors=1)),
    ]

    reviews = latest_reviews(records)

    assert reviews["a"]["edit_minutes"] == 7
    assert reviews["a"]["factual_errors"] == 1


def test_run_references_resolve_by_id_folder_name_prefix_or_bundle_path(tmp_path: Path) -> None:
    bundle = write_v010_failed_bundle(tmp_path / "3f0c9a1e-bundle-folder")
    records = [
        {"record": "run", "run_id": V010_RUN_ID, "bundle_path": str(bundle)},
        {"record": "run", "run_id": "11111111-9999-4000-8000-000000000000"},
    ]

    assert resolve_run_id(records, V010_RUN_ID) == V010_RUN_ID
    assert resolve_run_id(records, "11111111-2") == V010_RUN_ID
    assert resolve_run_id(records, str(bundle)) == V010_RUN_ID
    assert resolve_run_id(records, "3f0c9a1e-bundle-folder") == V010_RUN_ID
    assert resolve_run_id(records, "3f0c9a1e") == V010_RUN_ID
    with pytest.raises(LookupError, match="ambiguous"):
        resolve_run_id(records, "11111111")
    with pytest.raises(LookupError, match="no indexed run"):
        resolve_run_id(records, "ffffffff")
    with pytest.raises(LookupError, match="at least 8"):
        resolve_run_id(records, "1111111")


def _run_line(run_id: str) -> str:
    return json.dumps({"schema_version": "vidsnap.run-index/v1", "record": "run", "run_id": run_id})


def test_append_after_a_damaged_last_line_starts_a_new_line(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    index_path = runs_root / INDEX_FILE_NAME
    index_path.write_text(
        _run_line("first") + "\n" + '{"schema_version": "vidsnap.run-ind', encoding="utf-8"
    )

    append_index_record(runs_root, json.loads(_run_line("after-crash")))

    lines = index_path.read_text(encoding="utf-8").splitlines()
    assert lines[1] == '{"schema_version": "vidsnap.run-ind'
    assert json.loads(lines[2])["run_id"] == "after-crash"
    contents = read_index(runs_root)
    assert [record["run_id"] for record in contents.records] == ["first", "after-crash"]
    assert contents.invalid_lines == 1


def test_reading_counts_a_non_utf8_line_instead_of_failing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    (runs_root / INDEX_FILE_NAME).write_bytes(
        (_run_line("before") + "\n").encode()
        + b'{"schema_version": "vidsnap.run-index/v1", "record": "run", "run_id": "x\xff"}\n'
        + (_run_line("after") + "\n").encode()
    )

    contents = read_index(runs_root)

    assert [record["run_id"] for record in contents.records] == ["before", "after"]
    assert contents.invalid_lines == 1


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="needs symbolic links")
def test_a_symlinked_index_is_refused_for_append_and_read(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    target = tmp_path / "elsewhere.txt"
    target.write_text("not an index\n", encoding="utf-8")
    (runs_root / INDEX_FILE_NAME).symlink_to(target)

    with pytest.raises(OSError):
        append_index_record(runs_root, json.loads(_run_line("x")))
    with pytest.raises(OSError):
        read_index(runs_root)
    assert target.read_text(encoding="utf-8") == "not an index\n"


def test_new_index_files_are_private_to_the_user(tmp_path: Path) -> None:
    index_path = append_index_record(tmp_path / "runs", json.loads(_run_line("x")))

    assert index_path.stat().st_mode & 0o077 == 0
