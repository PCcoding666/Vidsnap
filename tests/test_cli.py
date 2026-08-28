"""CLI adapter boundary behavior."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vidsnap.cli import app
from vidsnap.contracts import TerminalState, VideoSource
from vidsnap.recipes.render import InterviewRecipeArtifacts
from vidsnap.recipes.runner import InterviewRecipeRunResult

_SENSITIVE_MARKER = "DO-NOT-ECHO-RECIPE-42"


class _FakeRecipeRunner:
    """Offline stand-in recording exactly what the CLI passes to the runner."""

    def __init__(self, result: InterviewRecipeRunResult, calls: list[tuple[VideoSource, Path]]):
        self._result = result
        self.calls = calls

    async def run(self, source: VideoSource, output_dir: Path) -> InterviewRecipeRunResult:
        self.calls.append((source, output_dir))
        return self._result


def _success_result(output_dir: Path) -> InterviewRecipeRunResult:
    return InterviewRecipeRunResult(
        terminal_state=TerminalState.SUCCEEDED,
        artifacts=InterviewRecipeArtifacts(
            transcript_path=output_dir / "transcript.zh.md",
            article_path=output_dir / "interview.article.md",
            brief_path=output_dir / "brief.md",
            trace_path=output_dir / "trace.html",
        ),
    )


def _blocked_result() -> InterviewRecipeRunResult:
    return InterviewRecipeRunResult(
        terminal_state=TerminalState.BLOCKED,
        failure_reason=f"credential unavailable ({_SENSITIVE_MARKER})",
    )


def test_cli_help_lists_recipe_command() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "recipe" in result.stdout


def test_recipe_help_lists_interview_command() -> None:
    result = CliRunner().invoke(app, ["recipe", "--help"])

    assert result.exit_code == 0
    assert "interview" in result.stdout


def test_recipe_interview_help_requires_local_video_and_output_dir_only() -> None:
    result = CliRunner().invoke(app, ["recipe", "interview", "--help"])

    assert result.exit_code == 0
    assert "video" in result.stdout.lower()
    assert "--output-dir" in result.stdout
    for forbidden in ("--model", "--prompt", "--url", "--budget", "--tool"):
        assert forbidden not in result.stdout


def test_recipe_interview_reports_success_with_exactly_four_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "interview.mp4"
    video_path.write_bytes(b"fake local video")
    out_dir = tmp_path / "recipe-out"
    calls: list[tuple[VideoSource, Path]] = []
    fake = _FakeRecipeRunner(_success_result(out_dir.resolve()), calls)
    monkeypatch.setattr("vidsnap.cli.InterviewRecipeRunner", lambda: fake)

    result = CliRunner().invoke(
        app,
        ["recipe", "interview", str(video_path), "--output-dir", str(out_dir)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["terminal_state"] == "SUCCEEDED"
    artifact_names = sorted(Path(artifact).name for artifact in payload["artifacts"])
    assert artifact_names == [
        "brief.md",
        "interview.article.md",
        "trace.html",
        "transcript.zh.md",
    ]
    assert len(calls) == 1
    passed_source, passed_output_dir = calls[0]
    assert isinstance(passed_source, VideoSource)
    assert passed_source.path == video_path.resolve()
    assert passed_output_dir == out_dir.resolve()


def test_recipe_interview_exits_one_on_succeeded_without_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "interview.mp4"
    video_path.write_bytes(b"fake local video")
    out_dir = tmp_path / "recipe-out"
    calls: list[tuple[VideoSource, Path]] = []
    fake = _FakeRecipeRunner(
        InterviewRecipeRunResult(terminal_state=TerminalState.SUCCEEDED, artifacts=None),
        calls,
    )
    monkeypatch.setattr("vidsnap.cli.InterviewRecipeRunner", lambda: fake)

    result = CliRunner().invoke(
        app,
        ["recipe", "interview", str(video_path), "--output-dir", str(out_dir)],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"terminal_state": "SUCCEEDED"}
    assert "artifacts" not in result.stdout
    assert "failure" not in result.stdout.lower()
    assert len(calls) == 1
    assert calls[0][0].path == video_path.resolve()
    assert calls[0][1] == out_dir.resolve()


def test_recipe_interview_exits_one_on_blocked_without_leaking_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "interview.mp4"
    video_path.write_bytes(b"fake local video")
    out_dir = tmp_path / "recipe-out"
    calls: list[tuple[VideoSource, Path]] = []
    fake = _FakeRecipeRunner(_blocked_result(), calls)
    monkeypatch.setattr("vidsnap.cli.InterviewRecipeRunner", lambda: fake)

    result = CliRunner().invoke(
        app,
        ["recipe", "interview", str(video_path), "--output-dir", str(out_dir)],
    )

    assert result.exit_code == 1
    assert _SENSITIVE_MARKER not in result.stdout
    assert len(calls) == 1
    assert calls[0][0].path == video_path.resolve()
    assert calls[0][1] == out_dir.resolve()


def test_cli_help_lists_harness_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "analyze" in result.stdout
    assert "benchmark" in result.stdout
    assert "conformance" in result.stdout
    assert "trace" in result.stdout
    assert "recipe" in result.stdout


def test_cli_help_exposes_trace_export() -> None:
    result = CliRunner().invoke(app, ["trace", "--help"])

    assert result.exit_code == 0
    assert "export" in result.stdout


def test_benchmark_commands_truthfully_report_blocked_without_local_key(monkeypatch) -> None:
    monkeypatch.delenv("VIDSNAP_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)

    for command in (["benchmark", "run"], ["benchmark", "compare"]):
        result = CliRunner().invoke(app, command)

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "BLOCKED_LIVE_BENCHMARK"
        assert "credential" in payload["reason"]
