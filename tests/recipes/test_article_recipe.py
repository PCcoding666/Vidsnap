"""The article recipe runs the t1 machinery offline and leaves an article plus a bundle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.ansi import strip_ansi
from vidsnap.cli import app
from vidsnap.contracts import TerminalState
from vidsnap.eval.adapters import FakeMedia
from vidsnap.recipes.article import ArticleRecipeRunner


@pytest.mark.asyncio
async def test_mock_article_recipe_writes_article_and_bundle(tmp_path: Path) -> None:
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"not-a-real-video")
    runner = ArticleRecipeRunner(
        system="harness+mock", media=FakeMedia(duration_seconds=120.0, has_audio=True)
    )

    result = await runner.run(
        video, "把这段视频改写成一篇图文并茂的文章。", tmp_path / "out", run_dir=tmp_path / "run"
    )

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.article_path == tmp_path / "out" / "article.md"
    assert result.article_path.is_file()
    assert (tmp_path / "out" / "output.json").is_file()
    assert (tmp_path / "run" / "result.json").is_file()
    header = json.loads((tmp_path / "run" / "events.jsonl").read_text().splitlines()[0])
    assert header["payload"]["recipe"]["id"] == "recipe/article"


def test_article_recipe_refuses_native_and_unknown_models() -> None:
    with pytest.raises(ValueError):
        ArticleRecipeRunner(system="native:qwen3.8-max")
    with pytest.raises(ValueError):
        ArticleRecipeRunner(system="harness+gpt-anything")


def test_recipe_article_help() -> None:
    result = CliRunner().invoke(app, ["recipe", "article", "--help"])

    assert result.exit_code == 0
    text = strip_ansi(result.stdout)
    for option in ("--goal", "--output-dir", "--model", "--endpoint"):
        assert option in text
