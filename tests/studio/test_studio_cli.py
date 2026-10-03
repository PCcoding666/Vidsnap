"""CLI boundary tests for `vidsnap studio export` (incremental, redacted)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vidsnap.cli import app


def test_root_help_lists_studio() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "studio" in result.stdout


def test_studio_help_lists_export() -> None:
    result = CliRunner().invoke(app, ["studio", "--help"])
    assert result.exit_code == 0
    assert "export" in result.stdout


def test_trace_help_still_lists_export() -> None:
    result = CliRunner().invoke(app, ["trace", "--help"])
    assert result.exit_code == 0
    assert "export" in result.stdout


def test_studio_export_succeeds_and_echoes_output_path(
    studio_manifest_path: Path, tmp_path: Path
) -> None:
    output = tmp_path / "eval-studio.html"

    result = CliRunner().invoke(
        app, ["studio", "export", str(studio_manifest_path), "-o", str(output)]
    )

    assert result.exit_code == 0
    assert str(output.resolve()) in result.stdout
    html = output.read_text(encoding="utf-8")
    assert "vidsnap.studio.projection/v1" in html
    assert html.count("<script") == 2


def test_studio_export_accepts_long_output_option(
    studio_manifest_path: Path, tmp_path: Path
) -> None:
    output = tmp_path / "long-form.html"

    result = CliRunner().invoke(
        app, ["studio", "export", str(studio_manifest_path), "--output", str(output)]
    )

    assert result.exit_code == 0
    assert output.is_file()


def test_invalid_manifest_exits_two_with_generic_category_and_no_output(tmp_path: Path) -> None:
    root = tmp_path / "invalid"
    root.mkdir()
    probe = "zqxwv-manifest-probe-value"
    manifest_path = root / "studio.json"
    manifest_path.write_text(
        json.dumps(
            {
                "api_version": "vidsnap.studio/v1",
                "title": probe,
                "iteration": {"agent_id": "x", "versions": "not-a-list"},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "never-written.html"

    result = CliRunner().invoke(app, ["studio", "export", str(manifest_path), "-o", str(output)])

    assert result.exit_code == 2
    assert "ERROR" in result.output
    assert probe not in result.output
    assert not output.exists()


def test_missing_manifest_exits_two_without_echoing_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "studio.json"
    output = tmp_path / "never-written.html"

    result = CliRunner().invoke(app, ["studio", "export", str(missing), "-o", str(output)])

    assert result.exit_code == 2
    assert "ERROR" in result.output
    assert str(missing) not in result.output
    assert not output.exists()


def test_dangling_reference_exits_two_without_echoing_the_reference(tmp_path: Path) -> None:
    root = tmp_path / "dangling"
    root.mkdir()
    reference = "runs/missing-zqxwv/t1"
    manifest_path = root / "studio.json"
    manifest_path.write_text(
        json.dumps(
            {
                "api_version": "vidsnap.studio/v1",
                "iteration": {
                    "agent_id": "video-summarizer",
                    "versions": [
                        {
                            "version": "v0",
                            "summary": "baseline",
                            "cases": [
                                {
                                    "case_id": "case-01",
                                    "trials": [{"trial_id": "t1", "run": reference}],
                                }
                            ],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "never-written.html"

    result = CliRunner().invoke(app, ["studio", "export", str(manifest_path), "-o", str(output)])

    assert result.exit_code == 2
    assert reference not in result.output
    assert not output.exists()


def test_credential_shaped_manifest_exits_two_without_echo(tmp_path: Path) -> None:
    root = tmp_path / "credential"
    root.mkdir()
    value = "Bearer zqxwv-credential"
    manifest_path = root / "studio.json"
    manifest_path.write_text(
        json.dumps(
            {
                "api_version": "vidsnap.studio/v1",
                "iteration": {
                    "agent_id": "video-summarizer",
                    "versions": [
                        {
                            "version": "v0",
                            "summary": value,
                            "cases": [
                                {
                                    "case_id": "case-01",
                                    "trials": [{"trial_id": "t1", "run": "runs/v0/case-01/t1"}],
                                }
                            ],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "never-written.html"

    result = CliRunner().invoke(app, ["studio", "export", str(manifest_path), "-o", str(output)])

    assert result.exit_code == 2
    assert value not in result.output
    assert "zqxwv" not in result.output
    assert not output.exists()


def test_non_empty_output_refusal_exits_two_and_preserves_the_file(
    studio_manifest_path: Path, tmp_path: Path
) -> None:
    output = tmp_path / "existing.html"
    original = "<html>existing operator content</html>"
    output.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(
        app, ["studio", "export", str(studio_manifest_path), "-o", str(output)]
    )

    assert result.exit_code == 2
    assert "ERROR" in result.output
    assert output.read_text(encoding="utf-8") == original
