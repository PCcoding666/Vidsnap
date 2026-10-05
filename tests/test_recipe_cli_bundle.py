"""`vidsnap recipe interview` keeps its RunBundle under a runs root and prints where."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.ansi import strip_ansi
from vidsnap.cli import app
from vidsnap.contracts import TerminalState, VideoSource
from vidsnap.recipes.runner import InterviewRecipeRunResult


class _RecordingRunner:
    """Offline stand-in that records the run_dir the CLI chose and reports it back."""

    def __init__(self, terminal_state: TerminalState) -> None:
        self.terminal_state = terminal_state
        self.run_dirs: list[Path | None] = []

    async def run(
        self, source: VideoSource, output_dir: Path, *, run_dir: Path | None = None
    ) -> InterviewRecipeRunResult:
        del source, output_dir
        self.run_dirs.append(run_dir)
        return InterviewRecipeRunResult(terminal_state=self.terminal_state, run_path=run_dir)


def _invoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: _RecordingRunner, *extra: str
) -> object:
    video = tmp_path / "interview.mp4"
    video.write_bytes(b"fake local video")
    monkeypatch.setattr("vidsnap.cli.InterviewRecipeRunner", lambda: runner)
    return CliRunner().invoke(
        app,
        ["recipe", "interview", str(video), "--output-dir", str(tmp_path / "out"), *extra],
    )


def test_failed_recipe_run_prints_where_its_bundle_was_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _RecordingRunner(TerminalState.PARTIAL)

    result = _invoke(tmp_path, monkeypatch, runner, "--runs-root", str(tmp_path / "runs"))

    assert result.exit_code == 1
    (run_dir,) = runner.run_dirs
    assert run_dir is not None
    assert run_dir.parent == (tmp_path / "runs").resolve()
    payload = json.loads(result.stdout)
    assert payload == {"terminal_state": "PARTIAL", "run_path": str(run_dir)}


def test_default_runs_root_is_run_under_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIDSNAP_RUNS_ROOT", raising=False)
    runner = _RecordingRunner(TerminalState.BLOCKED)

    _invoke(tmp_path, monkeypatch, runner)

    (run_dir,) = runner.run_dirs
    assert run_dir is not None and run_dir.parent == (tmp_path / "run").resolve()


def test_runs_root_can_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDSNAP_RUNS_ROOT", str(tmp_path / "env-runs"))
    runner = _RecordingRunner(TerminalState.BLOCKED)

    _invoke(tmp_path, monkeypatch, runner)

    (run_dir,) = runner.run_dirs
    assert run_dir is not None and run_dir.parent == (tmp_path / "env-runs").resolve()


def test_recipe_help_documents_the_runs_root() -> None:
    result = CliRunner().invoke(app, ["recipe", "interview", "--help"])

    assert result.exit_code == 0
    help_text = strip_ansi(result.stdout)
    assert "--runs-root" in help_text
    assert "VIDSNAP_RUNS_ROOT" in help_text
