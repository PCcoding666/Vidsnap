"""Bundles written by v0.1.0 and the packaged demo keep loading, replaying, and exporting.

All v0.1.1 trace additions are new optional payload keys, so a v0.1.0 ledger
must still parse, project, export, and summarize, with the new fields absent
or null rather than invented.
"""

from __future__ import annotations

import json
from pathlib import Path

from legacy_bundles import V010_RUN_ID, write_v010_failed_bundle
from typer.testing import CliRunner

from vidsnap.cli import app
from vidsnap.demo import replay_demo_run
from vidsnap.trace import read_trace
from vidsnap.trace.export import export_trace
from vidsnap.trace.run_index import summarize_run


def test_v010_bundle_still_projects_without_inventing_new_fields(tmp_path: Path) -> None:
    bundle = write_v010_failed_bundle(tmp_path / "v010")

    document = read_trace(bundle)

    assert document.run_id == V010_RUN_ID
    assert document.terminal_state == "FAILED"
    assert document.summary_only is False
    assert document.duration_ms == 690
    assert document.overview.goal is None
    assert document.overview.input_sha256 is None
    started = next(item for item in document.items if item.event_type == "tool.call.started")
    assert started.payload == {"name": "sample_evidence"}
    failed = next(item for item in document.items if item.event_type == "model.request.failed")
    assert failed.payload == {}
    assert failed.usage is None


def test_v010_bundle_still_exports_through_library_and_cli(tmp_path: Path) -> None:
    bundle = write_v010_failed_bundle(tmp_path / "v010")

    html = export_trace(bundle, tmp_path / "library.html").read_text(encoding="utf-8")
    result = CliRunner().invoke(
        app, ["trace", "export", str(bundle), "--output", str(tmp_path / "cli.html")]
    )

    assert V010_RUN_ID in html
    assert result.exit_code == 0, result.output
    assert V010_RUN_ID in (tmp_path / "cli.html").read_text(encoding="utf-8")


def test_v010_bundle_manifest_command_is_unchanged(tmp_path: Path) -> None:
    bundle = write_v010_failed_bundle(tmp_path / "v010")

    result = CliRunner().invoke(app, ["manifest", str(bundle)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["run_id"] == V010_RUN_ID


def test_packaged_demo_still_replays_exports_and_summarizes(tmp_path: Path) -> None:
    report = replay_demo_run(tmp_path / "demo")

    assert report.counts.steps == 6
    assert report.counts.evidence == 11
    assert (tmp_path / "demo" / "trace.html").is_file()
    exported = export_trace(tmp_path / "demo" / "run", tmp_path / "again.html")
    assert exported.is_file()
    record = summarize_run(tmp_path / "demo" / "run", command="demo")
    assert record["terminal_state"] == "SUCCEEDED"
    assert record["package_version"] == "0.1.0"
