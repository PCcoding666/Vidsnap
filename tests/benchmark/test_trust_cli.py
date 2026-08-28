"""Offline CLI contract for the deterministic trust evaluation command."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vidsnap.benchmark.trust import (
    RegisteredCase,
    TrustManifest,
    TrustMeasurement,
    TrustOutcome,
)
from vidsnap.cli import app

VARIANTS = ("direct", "harness")

METRIC_NAMES = (
    "temporal_grounding",
    "citation_precision",
    "unsupported_claim_rate",
    "evidence_coverage",
    "tool_budget_compliance",
    "provider_regression",
    "latency",
    "cost",
    "replay_determinism",
)

_SUMMARY = "benchmark infrastructure ready; current results are not statistically meaningful."
_CASE_ID = "case-trust-cli-42"


def _hex64(tag: int) -> str:
    return f"{tag:064x}"


def _case() -> RegisteredCase:
    return RegisteredCase(
        case_id=_CASE_ID,
        source_sha256=_hex64(1),
        input_fingerprint=_hex64(2),
        transcript_condition="verified",
        transcript_fingerprint=_hex64(3),
        model="qwen3.8-max",
        dataset="Video-MME",
        dataset_version="revision",
        available_evidence_fingerprint=_hex64(4),
        declared_evidence_fingerprints=(_hex64(4), _hex64(5)),
    )


def _outcome(case: RegisteredCase, variant: str) -> TrustOutcome:
    return TrustOutcome(
        case_id=case.case_id,
        variant=variant,
        source_sha256=case.source_sha256,
        input_fingerprint=case.input_fingerprint,
        transcript_condition=case.transcript_condition,
        transcript_fingerprint=case.transcript_fingerprint,
        model=case.model,
        dataset=case.dataset,
        dataset_version=case.dataset_version,
        available_evidence_fingerprint=case.available_evidence_fingerprint,
        used_evidence_fingerprints=(
            case.declared_evidence_fingerprints
            if variant == "harness"
            else (case.available_evidence_fingerprint,)
        ),
        measurement=TrustMeasurement(),
    )


def _payload() -> dict[str, object]:
    case = _case()
    manifest = TrustManifest(registered_cases=(case,), variants=VARIANTS)
    return {
        "manifest": manifest.model_dump(mode="json"),
        "outcomes": [_outcome(case, variant).model_dump(mode="json") for variant in VARIANTS],
    }


def _write_input(path: Path) -> Path:
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    return path


def _invoke(input_path: Path, report_path: Path) -> object:
    return CliRunner().invoke(
        app,
        ["benchmark", "evaluate", str(input_path), "--output", str(report_path)],
    )


def test_benchmark_evaluate_help_documents_input_and_output() -> None:
    result = CliRunner().invoke(app, ["benchmark", "evaluate", "--help"])

    assert result.exit_code == 0
    assert "INPUT_JSON" in result.stdout
    assert "--output" in result.stdout


def test_evaluate_writes_report_with_summary_and_nine_metrics_per_variant(
    tmp_path: Path,
) -> None:
    input_path = _write_input(tmp_path / "input.json")
    report_path = tmp_path / "report.json"

    result = _invoke(input_path, report_path)

    assert result.exit_code == 0
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"] == _SUMMARY
    assert set(payload["metrics"]) == set(VARIANTS)
    for variant_metrics in payload["metrics"].values():
        assert set(variant_metrics) == set(METRIC_NAMES)
    assert _CASE_ID not in result.stdout
    assert report_path.name in result.stdout


def test_evaluate_is_byte_identical_for_identical_input(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path / "input.json")
    first_report = tmp_path / "first.json"
    second_report = tmp_path / "second.json"

    first = _invoke(input_path, first_report)
    second = _invoke(input_path, second_report)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first_report.is_file() and second_report.is_file()
    assert first_report.read_bytes() == second_report.read_bytes()


def test_evaluate_needs_no_sockets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbid_socket(*args: object, **kwargs: object) -> None:
        raise AssertionError("trust evaluation must not open sockets")

    monkeypatch.setattr(socket, "socket", _forbid_socket)
    input_path = _write_input(tmp_path / "input.json")
    report_path = tmp_path / "report.json"

    result = _invoke(input_path, report_path)

    assert result.exit_code == 0
    assert report_path.is_file()


def test_evaluate_rejects_stale_manifest_sha_and_writes_no_output(tmp_path: Path) -> None:
    payload = _payload()
    manifest = payload["manifest"]
    assert isinstance(manifest, dict)
    manifest["manifest_sha256"] = "f" * 64
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    report_path = tmp_path / "report.json"

    result = _invoke(input_path, report_path)

    assert result.exit_code != 0
    assert not report_path.exists()


def test_evaluate_rejects_extra_top_level_field_and_writes_no_output(tmp_path: Path) -> None:
    payload = _payload()
    payload["unexpected"] = {"reason": "not allowed"}
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    report_path = tmp_path / "report.json"

    result = _invoke(input_path, report_path)

    assert result.exit_code != 0
    assert not report_path.exists()
