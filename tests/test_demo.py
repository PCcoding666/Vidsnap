"""Phase 2 acceptance tests: zero-key offline demo (RED batch).

These tests drive `vidsnap demo` through the existing Typer app only, so test
collection never imports a production module that does not exist yet. Until
Phase 2 lands, every invocation fails as a CLI/assertion failure. The chosen
output dir must hold a `vidsnap.demo/v1` demo report plus a real non-summary
RunBundle (`run/`) whose strict existing contracts are preserved:

- no provider key in the environment and a hard offline guard on sockets;
- explicit output that this is a packaged synthetic replay, not live model
  generation, naming the Final artifact and Trace and never a provider;
- `demo-report.json` (mode/counts/budget/provenance only, never the task
  result) next to `run/result.json` (strict VideoAnalysisResult, exactly 8
  claims), `run/evidence/` (exactly 11 strict evidence JSON items),
  `run/manifest.json` + `run/events.jsonl` (completed step numbers exactly
  1..6), and a fully offline `trace.html` exported from `run`;
- every claim's evidence references must exist among the replayed evidence;
- safe refusal to overwrite a non-empty output directory;
- publishable packaged fixture provenance (synthetic/self-owned or CC0) with
  no media, private data, or provider output.
"""

import json
import re
import socket
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from vidsnap.cli import app
from vidsnap.contracts.models import Evidence, VideoAnalysisResult
from vidsnap.loop.events import RunEvent
from vidsnap.trace.export import export_trace
from vidsnap.trace.reader import read_trace


@pytest.fixture(autouse=True)
def _no_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The demo must prove it needs no provider credential whatsoever."""
    monkeypatch.delenv("VIDSNAP_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _hard_offline_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn any network access attempt into an immediate test failure."""

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted during offline demo test")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


def _invoke_demo(output_dir: Path | None = None) -> Result:
    arguments = ["demo"]
    if output_dir is not None:
        arguments += ["--output-dir", str(output_dir)]
    return CliRunner().invoke(app, arguments)


def test_cli_help_lists_demo_command() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "demo" in result.stdout


def test_demo_runs_without_key_or_network_and_declares_synthetic_replay(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "vidsnap-demo"

    result = _invoke_demo(output_dir)

    assert result.exit_code == 0, result.output
    output_lower = result.output.lower()
    assert "replay" in output_lower
    assert "synthetic" in output_lower
    assert "packaged" in output_lower
    assert "not live model generation" in output_lower
    # The demo must surface every phase of the replay with user-visible labels.
    for label in (
        "goal",
        "agent steps",
        "tool calls",
        "evidence",
        "claims",
        "verification",
        "budget",
        "final artifact",
        "trace",
    ):
        assert label in output_lower, f"demo output must present: {label}"
    assert "qwen" not in output_lower
    assert "provider" not in output_lower


def test_demo_refuses_to_overwrite_non_empty_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "vidsnap-demo"
    output_dir.mkdir()
    sentinel = output_dir / "keep.txt"
    sentinel.write_text("do-not-delete", encoding="utf-8")

    result = _invoke_demo(output_dir)

    assert result.exit_code != 0
    output_lower = result.output.lower()
    assert any(word in output_lower for word in ("refus", "non-empty", "already exists"))
    assert sentinel.read_text(encoding="utf-8") == "do-not-delete"
    assert sorted(path.name for path in output_dir.iterdir()) == ["keep.txt"]


def test_demo_writes_demo_report_and_replay_bundle_layout(tmp_path: Path) -> None:
    output_dir = tmp_path / "chosen-output"

    result = _invoke_demo(output_dir)

    assert result.exit_code == 0, result.output

    report_path = output_dir / "demo-report.json"
    run_dir = output_dir / "run"
    assert report_path.is_file()
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "events.jsonl").is_file()
    assert (run_dir / "result.json").is_file()
    assert (output_dir / "trace.html").is_file()

    evidence_files = sorted((run_dir / "evidence").glob("*.json"))
    assert len(evidence_files) == 11

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["api_version"] == "vidsnap.demo/v1"
    assert report["mode"] == "replay"
    # The replay summary carries counts, never the task result itself.
    assert "summary" not in report
    assert "claims" not in report
    assert "required_sections" not in report


def test_demo_result_and_evidence_honor_strict_contracts(tmp_path: Path) -> None:
    output_dir = tmp_path / "vidsnap-demo"

    result = _invoke_demo(output_dir)

    assert result.exit_code == 0, result.output

    run_dir = output_dir / "run"
    analysis = VideoAnalysisResult.model_validate_json(
        (run_dir / "result.json").read_text(encoding="utf-8")
    )
    assert len(analysis.claims) == 8

    evidence_items = [
        Evidence.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((run_dir / "evidence").glob("*.json"))
    ]
    assert len(evidence_items) == 11
    evidence_ids = {item.id for item in evidence_items}
    assert len(evidence_ids) == len(evidence_items)

    for claim in analysis.claims:
        for reference in claim.evidence:
            assert reference.evidence_id in evidence_ids, (
                f"claim references missing evidence: {reference.evidence_id}"
            )


def test_demo_run_bundle_ledger_records_steps_one_through_six(tmp_path: Path) -> None:
    output_dir = tmp_path / "vidsnap-demo"

    result = _invoke_demo(output_dir)

    assert result.exit_code == 0, result.output

    run_dir = output_dir / "run"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)
    assert manifest.get("trace_schema") is not None, (
        "the demo must replay a real non-summary RunBundle, not a legacy result dir"
    )

    events = [
        RunEvent.model_validate(json.loads(line))
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    completed_steps = {
        event.step for event in events if event.status == "completed" and event.step is not None
    }
    assert completed_steps == set(range(1, 7))

    assert read_trace(run_dir).summary_only is False


def test_demo_trace_html_is_exported_from_run_and_fully_offline(tmp_path: Path) -> None:
    output_dir = tmp_path / "vidsnap-demo"

    result = _invoke_demo(output_dir)

    assert result.exit_code == 0, result.output

    trace_path = output_dir / "trace.html"
    html = trace_path.read_text(encoding="utf-8")
    assert len(html) > 0
    external_refs = re.findall(
        r"""(?:src|href)\s*=\s*["']https?://""",
        html,
        flags=re.IGNORECASE,
    )
    assert external_refs == [], "trace.html must not reference remote resources"
    assert "__VIDSNAP_" not in html, "trace template markers must be rendered away"

    reexport_path = tmp_path / "reexported-from-run.html"
    assert export_trace(output_dir / "run", reexport_path) == reexport_path
    assert reexport_path.read_bytes() == trace_path.read_bytes()


def test_demo_replay_report_matches_exact_counts_and_budget(tmp_path: Path) -> None:
    output_dir = tmp_path / "vidsnap-demo"

    result = _invoke_demo(output_dir)

    assert result.exit_code == 0, result.output

    output_lower = result.output.lower()
    assert "replayed 6 agent steps" in output_lower
    assert "loaded 11 evidence items" in output_lower
    assert "verified 8/8 claims" in output_lower
    assert "budget respected" in output_lower
    assert "trace exported" in output_lower

    # demo-report.json is the machine-checkable acceptance summary for the demo.
    report = json.loads((output_dir / "demo-report.json").read_text(encoding="utf-8"))
    assert report["api_version"] == "vidsnap.demo/v1"
    assert report["mode"] == "replay"
    counts = report["counts"]
    assert counts["steps"] == 6
    assert counts["evidence"] == 11
    assert counts["claims_total"] == 8
    assert counts["claims_grounded"] == 8
    assert report["budget"]["respected"] is True


def test_demo_declares_publishable_synthetic_fixture_provenance(tmp_path: Path) -> None:
    output_dir = tmp_path / "vidsnap-demo"

    result = _invoke_demo(output_dir)

    assert result.exit_code == 0, result.output

    report = json.loads((output_dir / "demo-report.json").read_text(encoding="utf-8"))
    provenance = report["provenance"]
    declared = {str(provenance.get("kind", "")).lower()}
    declared.add(str(provenance.get("license", "")).lower())
    allowed = {"synthetic", "self-owned", "cc0", "cc0-1.0", "public-domain"}
    assert declared & allowed, provenance
    assert provenance["contains_media"] is False
    assert provenance["contains_private_data"] is False
    assert provenance["contains_provider_output"] is False
