"""CLI runs append to a local run index; `vidsnap runs list` prints it as a table.

Every run here is offline: the CLI's harness and recipe runner are replaced by
instances wired to deterministic fakes and the offline MockProvider, so a key
present in the developer's environment can never cause a network call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.ansi import strip_ansi
from tests.recipes.test_interview_runner import FakeInterviewMedia, FakeInterviewTranscriber
from tests.runtime.fakes import FakeFFmpeg
from vidsnap.cli import app
from vidsnap.harness import VideoHarness
from vidsnap.providers import MockProvider
from vidsnap.recipes import InterviewRecipeRunner
from vidsnap.trace.run_index import INDEX_FILE_NAME, append_index_record


def _offline_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vidsnap.cli.VideoHarness",
        lambda: VideoHarness(media=FakeFFmpeg(has_audio=False), provider=MockProvider()),
    )


def _offline_recipe_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vidsnap.cli.InterviewRecipeRunner",
        lambda: InterviewRecipeRunner(
            media=FakeInterviewMedia(),
            recognizer=FakeInterviewTranscriber(),
            provider=MockProvider(),
        ),
    )


def _video(tmp_path: Path) -> Path:
    video = tmp_path / "input.mp4"
    video.write_bytes(b"deterministic-local-video-bytes")
    return video


def _index_lines(runs_root: Path) -> list[dict[str, object]]:
    text = (runs_root / INDEX_FILE_NAME).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _price_table(tmp_path: Path) -> Path:
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "vidsnap.price-table/v1",
                "currency": "CNY",
                "models": {
                    "mock": {"input_per_million_tokens": 1.0, "output_per_million_tokens": 2.0}
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_analyze_appends_one_index_line_with_cost_when_prices_are_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offline_harness(monkeypatch)
    runs_root = tmp_path / "runs"

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(_video(tmp_path)),
            "--runs-root",
            str(runs_root),
            "--price-table",
            str(_price_table(tmp_path)),
        ],
    )

    assert result.exit_code == 0, result.output
    printed = json.loads(result.stdout)
    assert set(printed) == {"terminal_state", "run_path", "claims"}
    run_path = Path(printed["run_path"])
    assert run_path.parent == runs_root.resolve()
    (record,) = _index_lines(runs_root)
    assert record["record"] == "run"
    assert record["command"] == "analyze"
    assert record["bundle_path"] == str(run_path.resolve())
    assert record["terminal_state"] == printed["terminal_state"]
    assert (record["provider"], record["model"]) == ("mock", "mock")
    cost = record["cost"]
    assert isinstance(cost, dict) and cost["complete"] is True and cost["currency"] == "CNY"


def test_analyze_without_prices_records_a_null_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offline_harness(monkeypatch)
    monkeypatch.delenv("VIDSNAP_PRICE_TABLE", raising=False)
    runs_root = tmp_path / "runs"

    result = CliRunner().invoke(
        app, ["analyze", str(_video(tmp_path)), "--runs-root", str(runs_root)]
    )

    assert result.exit_code == 0, result.output
    (record,) = _index_lines(runs_root)
    assert record["cost"] is None
    # MockProvider reports 3 input and 5 output tokens on every synthesis request.
    model_calls = record["model_calls"]
    assert isinstance(model_calls, int) and model_calls >= 1
    assert (record["input_tokens"], record["output_tokens"]) == (3 * model_calls, 5 * model_calls)
    assert record["tokens_reported"] is True


def test_analyze_output_dir_still_wins_and_is_indexed_under_the_runs_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offline_harness(monkeypatch)
    runs_root = tmp_path / "runs"
    output_dir = tmp_path / "elsewhere"

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(_video(tmp_path)),
            "--output-dir",
            str(output_dir),
            "--runs-root",
            str(runs_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / "manifest.json").is_file()
    (record,) = _index_lines(runs_root)
    assert record["bundle_path"] == str(output_dir.resolve())


def test_invalid_price_table_is_refused_before_any_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []
    monkeypatch.setattr("vidsnap.cli.VideoHarness", lambda: calls.append(1))
    bad = tmp_path / "prices.json"
    bad.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(_video(tmp_path)),
            "--runs-root",
            str(tmp_path / "runs"),
            "--price-table",
            str(bad),
        ],
    )

    assert result.exit_code == 2
    assert calls == []
    assert not (tmp_path / "runs").exists()


def test_failed_recipe_run_is_indexed_with_its_failure_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offline_recipe_runner(monkeypatch)
    runs_root = tmp_path / "runs"
    output_dir = tmp_path / "out"

    result = CliRunner().invoke(
        app,
        [
            "recipe",
            "interview",
            str(_video(tmp_path)),
            "--output-dir",
            str(output_dir),
            "--runs-root",
            str(runs_root),
        ],
    )

    # MockProvider's final answer is not an interview record: validation fails.
    assert result.exit_code == 1
    printed = json.loads(result.stdout)
    assert printed["terminal_state"] == "FAILED"
    assert not output_dir.exists()
    (record,) = _index_lines(runs_root)
    assert record["command"] == "recipe interview"
    assert record["recipe"] == "interview"
    assert record["failure_category"] == "validation"
    assert record["bundle_path"] == printed["run_path"]
    assert Path(printed["run_path"], "manifest.json").is_file()


def test_runs_list_prints_a_table_of_indexed_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _offline_harness(monkeypatch)
    runs_root = tmp_path / "runs"
    CliRunner().invoke(app, ["analyze", str(_video(tmp_path)), "--runs-root", str(runs_root)])
    (record,) = _index_lines(runs_root)

    result = CliRunner().invoke(app, ["runs", "list", "--runs-root", str(runs_root)])

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    for column in ("RUN", "STARTED", "COMMAND", "STATE", "TOKENS", "COST", "FAILURE", "BUNDLE"):
        assert column in lines[0]
    assert str(record["run_id"])[:8] in lines[1]
    assert "analyze" in lines[1]
    assert str(record["terminal_state"]) in lines[1]
    assert f"{record['input_tokens']}/{record['output_tokens']}" in lines[1]


def test_runs_list_on_an_empty_root_says_so(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["runs", "list", "--runs-root", str(tmp_path / "none")])

    assert result.exit_code == 0
    assert "No runs indexed" in result.stdout
    assert not (tmp_path / "none").exists()


def test_runs_list_marks_unreported_tokens_and_unpriced_cost(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    append_index_record(
        runs_root,
        {
            "schema_version": "vidsnap.run-index/v1",
            "record": "run",
            "run_id": "abcdef12-0000-4000-8000-000000000000",
            "started_at": "2026-10-06T01:02:03.456Z",
            "command": "recipe interview",
            "terminal_state": "FAILED",
            "duration_ms": 120500,
            "input_sha256": "f" * 64,
            "input_tokens": 0,
            "output_tokens": 0,
            "tokens_reported": False,
            "cost": {"amount": None, "currency": "CNY", "note": "usage_not_reported"},
            "failed_gates": None,
            "failure_category": "read_timeout",
            "bundle_path": "/tmp/bundle",
        },
    )

    result = CliRunner().invoke(app, ["runs", "list", "--runs-root", str(runs_root)])

    row = result.stdout.splitlines()[1]
    assert "abcdef12" in row
    assert "2026-10-06 01:02:03" in row
    assert "120.5s" in row
    assert "0/0?" in row
    assert "unknown" in row
    assert "read_timeout" in row


def test_runs_help_lists_the_list_command() -> None:
    result = CliRunner().invoke(app, ["runs", "--help"])

    assert result.exit_code == 0
    assert "list" in strip_ansi(result.stdout)


def test_analyze_help_documents_runs_root_and_price_table() -> None:
    result = CliRunner().invoke(app, ["analyze", "--help"])

    help_text = strip_ansi(result.stdout)
    for option in ("--runs-root", "--price-table", "VIDSNAP_RUNS_ROOT", "VIDSNAP_PRICE_TABLE"):
        assert option in help_text
