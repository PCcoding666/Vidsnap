"""`vidsnap runs review RUN` appends one human review record to the run index."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.ansi import strip_ansi
from vidsnap.cli import app
from vidsnap.trace.run_index import INDEX_FILE_NAME, append_index_record

_RUN_ID = "5e1f0c2a-7b3d-4e9f-8a21-0c6d4b2e9f10"


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    runs_root = tmp_path / "runs"
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    append_index_record(
        runs_root,
        {
            "schema_version": "vidsnap.run-index/v1",
            "record": "run",
            "run_id": _RUN_ID,
            "command": "recipe interview",
            "terminal_state": "SUCCEEDED",
            "bundle_path": str(bundle.resolve()),
        },
    )
    return runs_root, bundle


def _lines(runs_root: Path) -> list[dict[str, object]]:
    text = (runs_root / INDEX_FILE_NAME).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_review_appends_every_business_effect_field(tmp_path: Path) -> None:
    runs_root, _ = _seed(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "runs",
            "review",
            _RUN_ID[:8],
            "--runs-root",
            str(runs_root),
            "--edit-minutes",
            "12.5",
            "--published",
            "--factual-errors",
            "1",
            "--images-replaced",
            "2",
            "--note",
            "Fixed one wrong date; swapped two near-blank frames.",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "status": "REVIEWED",
        "run_id": _RUN_ID,
        "index": str((runs_root / INDEX_FILE_NAME).resolve()),
    }
    run_line, review = _lines(runs_root)
    assert run_line["record"] == "run"
    assert review["schema_version"] == "vidsnap.run-index/v1"
    assert review["record"] == "review"
    assert review["run_id"] == _RUN_ID
    assert review["edit_minutes"] == 12.5
    assert review["published"] is True
    assert review["factual_errors"] == 1
    assert review["images_replaced"] == 2
    assert review["note"] == "Fixed one wrong date; swapped two near-blank frames."
    assert isinstance(review["reviewed_at"], str)


def test_partial_review_keeps_unrecorded_fields_null(tmp_path: Path) -> None:
    runs_root, bundle = _seed(tmp_path)

    result = CliRunner().invoke(
        app, ["runs", "review", str(bundle), "--runs-root", str(runs_root), "--not-published"]
    )

    assert result.exit_code == 0, result.output
    review = _lines(runs_root)[-1]
    assert review["published"] is False
    assert review["edit_minutes"] is None
    assert review["factual_errors"] is None
    assert review["images_replaced"] is None
    assert review["note"] is None


def test_runs_list_shows_the_latest_review(tmp_path: Path) -> None:
    runs_root, _ = _seed(tmp_path)
    for minutes in ("5", "9"):
        CliRunner().invoke(
            app,
            ["runs", "review", _RUN_ID, "--runs-root", str(runs_root), "--edit-minutes", minutes],
        )

    result = CliRunner().invoke(app, ["runs", "list", "--runs-root", str(runs_root)])

    lines = result.stdout.splitlines()
    assert len(lines) == 2, "reviews must not appear as extra run rows"
    assert "9 min edit" in lines[1]
    assert "5 min edit" not in lines[1]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["ffffffff", "--published"], "no indexed run"),
        (["5e1f", "--published", "--edit-minutes", "1"], None),
        ([_RUN_ID], "at least one"),
        ([_RUN_ID, "--edit-minutes", "-1"], None),
        ([_RUN_ID, "--factual-errors", "-2"], None),
    ],
)
def test_invalid_reviews_are_refused_without_writing(
    tmp_path: Path, arguments: list[str], message: str | None
) -> None:
    runs_root, _ = _seed(tmp_path)
    append_index_record(
        runs_root,
        {
            "schema_version": "vidsnap.run-index/v1",
            "record": "run",
            "run_id": "5e1f9999-0000-4000-8000-000000000000",
        },
    )
    before = (runs_root / INDEX_FILE_NAME).read_text(encoding="utf-8")

    result = CliRunner().invoke(app, ["runs", "review", *arguments, "--runs-root", str(runs_root)])

    assert result.exit_code == 2
    if message is not None:
        assert message in result.output
    assert (runs_root / INDEX_FILE_NAME).read_text(encoding="utf-8") == before


def test_ambiguous_prefix_is_refused(tmp_path: Path) -> None:
    runs_root, _ = _seed(tmp_path)
    append_index_record(
        runs_root,
        {
            "schema_version": "vidsnap.run-index/v1",
            "record": "run",
            "run_id": "5e1f0c2a-0000-4000-8000-000000000000",
        },
    )

    result = CliRunner().invoke(
        app, ["runs", "review", "5e1f0c2a", "--runs-root", str(runs_root), "--published"]
    )

    assert result.exit_code == 2
    assert "ambiguous" in result.output


def test_review_help_lists_every_field() -> None:
    result = CliRunner().invoke(app, ["runs", "review", "--help"])

    assert result.exit_code == 0
    help_text = strip_ansi(result.stdout)
    for option in (
        "--edit-minutes",
        "--published",
        "--not-published",
        "--factual-errors",
        "--images-replaced",
        "--note",
        "--runs-root",
    ):
        assert option in help_text


def test_review_by_bundle_folder_name(tmp_path: Path) -> None:
    runs_root, bundle = _seed(tmp_path)

    result = CliRunner().invoke(
        app, ["runs", "review", bundle.name, "--runs-root", str(runs_root), "--published"]
    )

    assert result.exit_code == 0, result.output
    assert _lines(runs_root)[-1]["run_id"] == _RUN_ID


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores file permissions"
)
def test_review_on_a_read_only_index_fails_with_one_line(tmp_path: Path) -> None:
    runs_root, _ = _seed(tmp_path)
    index_path = runs_root / INDEX_FILE_NAME
    index_path.chmod(stat.S_IRUSR)
    try:
        result = CliRunner().invoke(
            app, ["runs", "review", _RUN_ID, "--runs-root", str(runs_root), "--published"]
        )
    finally:
        index_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert result.exit_code == 2
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output
    assert result.output.strip().splitlines() == [
        f"Review refused: run index not writable: {index_path.resolve()}"
    ]


def test_runs_list_refuses_a_symlinked_index_with_one_line(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    target = tmp_path / "elsewhere.jsonl"
    target.write_text("", encoding="utf-8")
    (runs_root / INDEX_FILE_NAME).symlink_to(target)

    result = CliRunner().invoke(app, ["runs", "list", "--runs-root", str(runs_root)])

    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert len(result.output.strip().splitlines()) == 1
    assert "run index" in result.output
