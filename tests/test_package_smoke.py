"""Public package entry-point contracts.

This catches a broken distribution layout where the documented import or CLI
entry point cannot be discovered by an installed user.
"""

from typer.testing import CliRunner

from vidsnap import __version__
from vidsnap.cli import app


def test_package_exposes_version_and_cli_app() -> None:
    assert __version__ == "0.1.0"
    assert app.info.name == "vidsnap"


def test_cli_help_is_available_from_the_installed_entry_point() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "VidSnap Harness" in result.stdout
