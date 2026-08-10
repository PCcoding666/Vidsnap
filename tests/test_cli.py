"""CLI adapter boundary behavior."""

from typer.testing import CliRunner

from vidsnap.cli import app


def test_cli_help_lists_harness_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "analyze" in result.stdout
    assert "benchmark" in result.stdout
    assert "conformance" in result.stdout
