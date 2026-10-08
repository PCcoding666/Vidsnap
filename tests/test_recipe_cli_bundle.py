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


def _real_runner_that_verifies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire the real recipe runner to offline fakes whose final answer passes every gate."""
    from tests.recipes.test_interview_runner import (
        FakeInterviewMedia,
        FakeInterviewTranscriber,
        ScriptedInterviewAgent,
        interview_final_payload,
    )
    from vidsnap.config import HarnessConfig
    from vidsnap.contracts import AgentDecision, ToolCallRequest
    from vidsnap.recipes import InterviewRecipeRunner

    def build() -> InterviewRecipeRunner:
        agent = ScriptedInterviewAgent(
            [
                AgentDecision(
                    kind="tool_calls",
                    calls=(ToolCallRequest(name="transcribe_audio", arguments={}),),
                ),
                AgentDecision(
                    kind="tool_calls",
                    calls=(ToolCallRequest(name="sample_evidence", arguments={"max_frames": 1}),),
                ),
                AgentDecision(kind="final", output=interview_final_payload()),
            ]
        )
        return InterviewRecipeRunner(
            config=HarnessConfig(api_key=None),
            media=FakeInterviewMedia(),
            recognizer=FakeInterviewTranscriber(),
            agent_model=agent,
        )

    monkeypatch.setattr("vidsnap.cli.InterviewRecipeRunner", build)


def test_index_records_the_command_outcome_when_it_differs_from_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _real_runner_that_verifies(monkeypatch)

    def refuse_to_write(*args: object, **kwargs: object) -> object:
        raise OSError("simulated full disk")

    monkeypatch.setattr("vidsnap.recipes.runner.render_interview_recipe", refuse_to_write)
    video = tmp_path / "interview.mp4"
    video.write_bytes(b"fake local video")
    runs_root = tmp_path / "runs"

    result = CliRunner().invoke(
        app,
        [
            "recipe",
            "interview",
            str(video),
            "--output-dir",
            str(tmp_path / "out"),
            "--runs-root",
            str(runs_root),
        ],
    )

    assert result.exit_code == 1
    printed = json.loads(result.stdout)
    (line,) = (runs_root / "index.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    # The verified kernel run finished SUCCEEDED, but the command failed afterwards.
    assert record["bundle_terminal_state"] == "SUCCEEDED"
    assert printed["terminal_state"] == "FAILED"
    assert record["terminal_state"] == printed["terminal_state"]
    assert record["failure_reason"] == "unexpected recipe runner error"
    assert record["failure_category"] == "unknown"


def test_index_outcome_matches_the_command_when_they_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _real_runner_that_verifies(monkeypatch)
    video = tmp_path / "interview.mp4"
    video.write_bytes(b"fake local video")
    runs_root = tmp_path / "runs"

    result = CliRunner().invoke(
        app,
        [
            "recipe",
            "interview",
            str(video),
            "--output-dir",
            str(tmp_path / "out"),
            "--runs-root",
            str(runs_root),
        ],
    )

    assert result.exit_code == 0, result.output
    record = json.loads((runs_root / "index.jsonl").read_text(encoding="utf-8"))
    assert record["terminal_state"] == record["bundle_terminal_state"] == "SUCCEEDED"
    assert json.loads(result.stdout)["terminal_state"] == "SUCCEEDED"
    assert record["failure_reason"] is None


def test_non_empty_output_dir_is_refused_before_any_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _RecordingRunner(TerminalState.SUCCEEDED)
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "draft.md").write_text("keep me", encoding="utf-8")

    result = _invoke(tmp_path, monkeypatch, runner, "--runs-root", str(tmp_path / "runs"))

    assert result.exit_code == 2
    assert runner.run_dirs == []
    assert "output directory is not empty" in result.output.lower()
    assert (output_dir / "draft.md").read_text(encoding="utf-8") == "keep me"
    assert not (tmp_path / "runs").exists()


def test_no_keep_bundle_restores_the_temporary_bundle_and_writes_no_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _RecordingRunner(TerminalState.SUCCEEDED)
    runs_root = tmp_path / "runs"

    result = _invoke(
        tmp_path, monkeypatch, runner, "--runs-root", str(runs_root), "--no-keep-bundle"
    )

    assert result.exit_code == 1  # the recording runner returns no artifacts
    assert runner.run_dirs == [None]
    assert "run_path" not in json.loads(result.stdout)
    assert not runs_root.exists()


def test_no_keep_bundle_leaves_no_bundle_on_disk_with_the_real_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _real_runner_that_verifies(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIDSNAP_RUNS_ROOT", raising=False)
    video = tmp_path / "interview.mp4"
    video.write_bytes(b"fake local video")

    result = CliRunner().invoke(
        app,
        [
            "recipe",
            "interview",
            str(video),
            "--output-dir",
            str(tmp_path / "out"),
            "--no-keep-bundle",
        ],
    )

    assert result.exit_code == 0, result.output
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["interview.mp4", "out"]
    assert len(list((tmp_path / "out").iterdir())) == 4


def test_recipe_help_documents_the_keep_bundle_opt_out() -> None:
    result = CliRunner().invoke(app, ["recipe", "interview", "--help"])

    assert "--no-keep-bundle" in strip_ansi(result.stdout)
