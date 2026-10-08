"""The runs root is prepared before any run starts, and failures say why.

A read-only working directory makes the default runs root (./run) impossible
to create. Commands that need it must refuse before any model call with a
one-line reason, instead of running nothing and printing a bare FAILED.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.recipes.test_interview_runner import FakeInterviewMedia
from tests.runtime.fakes import FakeFFmpeg
from vidsnap.cli import app
from vidsnap.config import HarnessConfig
from vidsnap.harness import VideoHarness
from vidsnap.providers import MockProvider
from vidsnap.recipes import InterviewRecipeRunner

pytestmark = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory permissions"
)


@pytest.fixture
def read_only_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    workdir = tmp_path / "read-only"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.delenv("VIDSNAP_RUNS_ROOT", raising=False)
    workdir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        yield workdir
    finally:
        workdir.chmod(stat.S_IRWXU)


def _video(tmp_path: Path) -> Path:
    video = tmp_path / "input.mp4"
    video.write_bytes(b"deterministic-local-video-bytes")
    return video


def test_recipe_refuses_an_unwritable_default_runs_root_before_running(
    tmp_path: Path, read_only_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []
    monkeypatch.setattr("vidsnap.cli.InterviewRecipeRunner", lambda: calls.append(1))

    result = CliRunner().invoke(
        app,
        ["recipe", "interview", str(_video(tmp_path)), "--output-dir", str(tmp_path / "out")],
    )

    assert result.exit_code == 2
    assert calls == []
    expected = f"runs root not writable: {(read_only_cwd / 'run').resolve()}; pass --runs-root"
    assert expected in result.output
    assert not (read_only_cwd / "run").exists()


def test_analyze_refuses_an_unwritable_default_runs_root_before_running(
    tmp_path: Path, read_only_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []
    monkeypatch.setattr("vidsnap.cli.VideoHarness", lambda: calls.append(1))

    result = CliRunner().invoke(app, ["analyze", str(_video(tmp_path))])

    assert result.exit_code == 2
    assert calls == []
    assert "runs root not writable" in result.output


def test_analyze_with_output_dir_still_runs_and_only_warns_about_the_index(
    tmp_path: Path, read_only_cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del read_only_cwd
    monkeypatch.setattr(
        "vidsnap.cli.VideoHarness",
        lambda: VideoHarness(media=FakeFFmpeg(has_audio=False), provider=MockProvider()),
    )
    output_dir = tmp_path / "bundle"

    result = CliRunner().invoke(
        app, ["analyze", str(_video(tmp_path)), "--output-dir", str(output_dir)]
    )

    assert result.exit_code == 0
    assert (output_dir / "manifest.json").is_file()
    assert "Run index not updated" in result.output


def test_recipe_failure_json_carries_the_fixed_failure_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The default Qwen stack without a key blocks before any request is sent.
    monkeypatch.setattr(
        "vidsnap.cli.InterviewRecipeRunner",
        lambda: InterviewRecipeRunner(
            config=HarnessConfig(api_key=None), media=FakeInterviewMedia()
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "recipe",
            "interview",
            str(_video(tmp_path)),
            "--output-dir",
            str(tmp_path / "out"),
            "--runs-root",
            str(tmp_path / "runs"),
        ],
    )

    assert result.exit_code == 1
    printed = json.loads(result.stdout)
    assert printed["terminal_state"] == "BLOCKED"
    assert printed["failure_reason"] == "provider unavailable"
    assert Path(printed["run_path"], "manifest.json").is_file()
