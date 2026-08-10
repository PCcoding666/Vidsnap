"""CLI adapter boundary behavior."""

import json

from typer.testing import CliRunner

from vidsnap.cli import app


def test_cli_help_lists_harness_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "analyze" in result.stdout
    assert "benchmark" in result.stdout
    assert "conformance" in result.stdout


def test_benchmark_commands_truthfully_report_blocked_without_local_key(monkeypatch) -> None:
    monkeypatch.delenv("VIDSNAP_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)

    for command in (["benchmark", "run"], ["benchmark", "compare"]):
        result = CliRunner().invoke(app, command)

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "BLOCKED_LIVE_BENCHMARK"
        assert "credential" in payload["reason"]
