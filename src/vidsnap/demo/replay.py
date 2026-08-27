"""Zero-key offline replay of the packaged synthetic demo run."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import shutil
from dataclasses import dataclass
from importlib import resources
from importlib.abc import Traversable
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field, ValidationError

from vidsnap.contracts.models import (
    Evidence,
    HarnessPolicy,
    StrictModel,
    VideoAnalysisResult,
)
from vidsnap.loop.events import EventUsage, RunEvent
from vidsnap.trace.export import export_trace
from vidsnap.trace.reader import read_trace

_API_VERSION: Literal["vidsnap.demo/v1"] = "vidsnap.demo/v1"
_MODE: Literal["replay"] = "replay"
_FIXTURE_PACKAGE = "vidsnap.demo"
_RUN_DIR_NAME = "run"
_REPORT_NAME = "demo-report.json"
_TRACE_NAME = "trace.html"
_EXPECTED_COMPLETED_STEPS = frozenset(range(1, 7))
_EXPECTED_EVIDENCE_COUNT = 11
_EXPECTED_CLAIMS_TOTAL = 8
_EXPECTED_CLAIMS_GROUNDED = 8
_SHA256_HEX = re.compile(r"[0-9a-fA-F]{64}")


class DemoReplayProvenance(StrictModel):
    """Publishable origin declaration for the packaged demo fixtures."""

    kind: Literal["synthetic", "self-owned"]
    license: Literal["CC0-1.0", "CC0", "public-domain"]
    contains_media: bool
    contains_private_data: bool
    contains_provider_output: bool


class DemoReplayCounts(StrictModel):
    steps: int = Field(ge=0)
    evidence: int = Field(ge=0)
    claims_total: int = Field(ge=0)
    claims_grounded: int = Field(ge=0)


class DemoReplayBudget(StrictModel):
    respected: bool
    max_iterations: int
    max_model_calls: int
    max_tool_calls: int
    max_evidence_frames: int
    max_wall_seconds: int
    model_calls: int
    tool_calls: int
    evidence_frames: int
    wall_seconds: int


class DemoReplayReport(StrictModel):
    """Machine-checkable acceptance summary for one demo replay."""

    api_version: Literal["vidsnap.demo/v1"]
    mode: Literal["replay"]
    counts: DemoReplayCounts
    budget: DemoReplayBudget
    provenance: DemoReplayProvenance


@dataclass(frozen=True)
class _ReplayBundle:
    files: dict[str, bytes]
    manifest: dict[str, Any]
    events: list[RunEvent]
    evidence: list[Evidence]
    result: VideoAnalysisResult
    provenance: DemoReplayProvenance
    policy: HarnessPolicy
    usage: EventUsage


def replay_demo_run(output_dir: Path) -> DemoReplayReport:
    """Replay the packaged synthetic demo into ``output_dir`` without any model call.

    Validates provenance, manifest hashes, the RunEvent ledger, evidence and
    claim counts, and HarnessPolicy bounds before publishing ``run/``,
    ``trace.html``, and ``demo-report.json``. A non-empty output directory is
    refused; only a directory newly created by this call is removed on failure.
    """
    target = output_dir.expanduser().resolve()
    pre_existing = target.exists()
    if pre_existing:
        if not target.is_dir():
            raise FileExistsError(f"refusing to overwrite non-directory output path: {target}")
        if any(target.iterdir()):
            raise FileExistsError(f"refusing to overwrite non-empty output directory: {target}")

    bundle = _load_fixture_bundle()
    try:
        target.mkdir(parents=True, exist_ok=True)
        _materialize_bundle(target / _RUN_DIR_NAME, bundle)
        document = read_trace(target / _RUN_DIR_NAME)
        if document.summary_only:
            raise ValueError("demo replay requires a non-summary step-level trace")
        report = _build_report(bundle, document)
        export_trace(target / _RUN_DIR_NAME, target / _TRACE_NAME)
        (target / _REPORT_NAME).write_text(
            report.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        _remove_partial_output(target, pre_existing)
        raise
    return report


def _load_fixture_bundle() -> _ReplayBundle:
    package_root = resources.files(_FIXTURE_PACKAGE)
    provenance = _load_provenance(package_root / "fixtures" / "provenance.json")
    run_root = package_root / "fixtures" / _RUN_DIR_NAME
    if not run_root.is_dir():
        raise ValueError("packaged demo fixtures are missing the run bundle")
    bundle_files: dict[str, bytes] = {}
    _collect_files(run_root, "", bundle_files)
    for rel_path in bundle_files:
        _require_safe_relative_path(rel_path)
    if "manifest.json" not in bundle_files:
        raise ValueError("packaged demo run bundle is missing manifest.json")
    if "events.jsonl" not in bundle_files:
        raise ValueError("packaged demo run bundle is missing events.jsonl")
    if "result.json" not in bundle_files:
        raise ValueError("packaged demo run bundle is missing result.json")

    manifest = _load_manifest(bundle_files)
    _validate_file_hashes(manifest, bundle_files)
    events, usage = _load_events(bundle_files)
    policy = _load_policy(manifest)
    _validate_usage_bounds(usage, policy)
    evidence = _load_evidence(bundle_files)
    result = _load_result(bundle_files, {item.id for item in evidence})
    _validate_completed_steps(events)
    return _ReplayBundle(
        files=bundle_files,
        manifest=manifest,
        events=events,
        evidence=evidence,
        result=result,
        provenance=provenance,
        policy=policy,
        usage=usage,
    )


def _load_provenance(node: Traversable) -> DemoReplayProvenance:
    try:
        raw = json.loads(node.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("packaged demo provenance is missing or unreadable") from error
    try:
        provenance = DemoReplayProvenance.model_validate(raw)
    except ValidationError as error:
        raise ValueError("packaged demo provenance is not publishable") from error
    if (
        provenance.contains_media
        or provenance.contains_private_data
        or provenance.contains_provider_output
    ):
        raise ValueError(
            "packaged demo provenance must exclude media, private data, and provider output"
        )
    return provenance


def _collect_files(root: Traversable, prefix: str, out: dict[str, bytes]) -> None:
    for entry in root.iterdir():
        rel_path = f"{prefix}{entry.name}"
        if entry.is_dir():
            _collect_files(entry, f"{rel_path}/", out)
        else:
            out[rel_path] = entry.read_bytes()


def _require_safe_relative_path(rel_path: str) -> None:
    parts = PurePosixPath(rel_path).parts
    if not parts or parts[0] == "/" or ".." in parts:
        raise ValueError(f"packaged demo fixture has an unsafe path: {rel_path}")


def _load_manifest(bundle_files: dict[str, bytes]) -> dict[str, Any]:
    try:
        manifest = json.loads(bundle_files["manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("packaged demo run manifest is unreadable") from error
    if not isinstance(manifest, dict):
        raise ValueError("packaged demo run manifest is unreadable")
    if manifest.get("trace_schema") is None:
        raise ValueError("packaged demo run manifest must record a trace schema")
    return manifest


def _validate_file_hashes(manifest: dict[str, Any], bundle_files: dict[str, bytes]) -> None:
    recorded = manifest.get("files")
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("run manifest must record sha256 hashes for bundle files")
    for rel_path, payload in bundle_files.items():
        if rel_path == "manifest.json":
            continue
        entry = recorded.get(rel_path)
        digest = _expected_digest(entry)
        if digest is None:
            raise ValueError(f"run manifest is missing a sha256 hash for {rel_path}")
        actual = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(digest.lower(), actual):
            raise ValueError(f"packaged demo file failed its manifest hash check: {rel_path}")
        expected_size = _expected_size(entry)
        if expected_size is not None and expected_size != len(payload):
            raise ValueError(f"packaged demo file has an unexpected size: {rel_path}")


def _expected_digest(entry: object) -> str | None:
    if isinstance(entry, str) and _SHA256_HEX.fullmatch(entry):
        return entry
    if isinstance(entry, dict):
        value = entry.get("sha256")
        if isinstance(value, str) and _SHA256_HEX.fullmatch(value):
            return value
    return None


def _expected_size(entry: object) -> int | None:
    if isinstance(entry, dict):
        value = entry.get("bytes")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _load_events(bundle_files: dict[str, bytes]) -> tuple[list[RunEvent], EventUsage]:
    events: list[RunEvent] = []
    usage_total: EventUsage | None = None
    previous_sequence = 0
    lines = bundle_files["events.jsonl"].decode("utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = RunEvent.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            raise ValueError(f"invalid demo ledger entry at line {line_number}") from error
        if event.sequence <= previous_sequence:
            raise ValueError("demo ledger sequences must strictly increase")
        previous_sequence = event.sequence
        if event.usage is not None:
            usage_total = event.usage if usage_total is None else usage_total + event.usage
        events.append(event)
    if not events:
        raise ValueError("packaged demo ledger is empty")
    return events, usage_total if usage_total is not None else EventUsage()


def _validate_completed_steps(events: list[RunEvent]) -> None:
    completed = {
        event.step for event in events if event.status == "completed" and event.step is not None
    }
    if completed != _EXPECTED_COMPLETED_STEPS:
        raise ValueError(
            f"demo ledger must record completed steps exactly 1..6, found {sorted(completed)}"
        )


def _load_evidence(bundle_files: dict[str, bytes]) -> list[Evidence]:
    evidence: list[Evidence] = []
    seen_ids: set[str] = set()
    evidence_paths = sorted(
        rel_path
        for rel_path in bundle_files
        if rel_path.startswith("evidence/") and rel_path.endswith(".json")
    )
    for rel_path in evidence_paths:
        try:
            item = Evidence.model_validate(json.loads(bundle_files[rel_path].decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError) as error:
            raise ValueError(f"invalid demo evidence item: {rel_path}") from error
        if item.id in seen_ids:
            raise ValueError(f"duplicate demo evidence id: {item.id}")
        seen_ids.add(item.id)
        evidence.append(item)
    if len(evidence) != _EXPECTED_EVIDENCE_COUNT:
        raise ValueError(
            f"demo must package exactly {_EXPECTED_EVIDENCE_COUNT} evidence items, "
            f"found {len(evidence)}"
        )
    return evidence


def _load_result(bundle_files: dict[str, bytes], evidence_ids: set[str]) -> VideoAnalysisResult:
    try:
        result = VideoAnalysisResult.model_validate_json(
            bundle_files["result.json"].decode("utf-8")
        )
    except (UnicodeDecodeError, ValidationError) as error:
        raise ValueError("packaged demo result is not a strict VideoAnalysisResult") from error
    grounded = sum(
        1
        for claim in result.claims
        if all(reference.evidence_id in evidence_ids for reference in claim.evidence)
    )
    if len(result.claims) != _EXPECTED_CLAIMS_TOTAL:
        raise ValueError(
            f"demo result must hold exactly {_EXPECTED_CLAIMS_TOTAL} claims, "
            f"found {len(result.claims)}"
        )
    if grounded != _EXPECTED_CLAIMS_GROUNDED:
        raise ValueError(
            f"demo result must ground exactly {_EXPECTED_CLAIMS_GROUNDED} claims "
            f"in packaged evidence, found {grounded}"
        )
    return result


def _load_policy(manifest: dict[str, Any]) -> HarnessPolicy:
    raw = manifest.get("policy")
    if raw is None:
        return HarnessPolicy()
    if not isinstance(raw, dict):
        raise ValueError("run manifest policy must be an object")
    try:
        return HarnessPolicy.model_validate(raw)
    except ValidationError as error:
        raise ValueError("run manifest policy violates HarnessPolicy bounds") from error


def _validate_usage_bounds(usage: EventUsage, policy: HarnessPolicy) -> None:
    if usage.model_calls != 0:
        raise ValueError("demo replay must record zero model calls")
    if usage.tool_calls > policy.max_tool_calls:
        raise ValueError("replayed demo usage exceeds the HarnessPolicy tool-call bound")
    if usage.evidence_frames > policy.max_evidence_frames:
        raise ValueError("replayed demo usage exceeds the HarnessPolicy evidence-frame bound")


def _build_report(bundle: _ReplayBundle, document: Any) -> DemoReplayReport:
    policy = bundle.policy
    usage = bundle.usage
    wall_seconds = math.ceil((document.duration_ms or 0) / 1000)
    respected = (
        usage.model_calls <= policy.max_model_calls
        and usage.tool_calls <= policy.max_tool_calls
        and usage.evidence_frames <= policy.max_evidence_frames
        and wall_seconds <= policy.max_wall_seconds
    )
    if not respected:
        raise ValueError("replayed demo run exceeded its HarnessPolicy bounds")
    return DemoReplayReport(
        api_version=_API_VERSION,
        mode=_MODE,
        counts=DemoReplayCounts(
            steps=len(_EXPECTED_COMPLETED_STEPS),
            evidence=len(bundle.evidence),
            claims_total=len(bundle.result.claims),
            claims_grounded=_EXPECTED_CLAIMS_GROUNDED,
        ),
        budget=DemoReplayBudget(
            respected=True,
            max_iterations=policy.max_iterations,
            max_model_calls=policy.max_model_calls,
            max_tool_calls=policy.max_tool_calls,
            max_evidence_frames=policy.max_evidence_frames,
            max_wall_seconds=policy.max_wall_seconds,
            model_calls=usage.model_calls,
            tool_calls=usage.tool_calls,
            evidence_frames=usage.evidence_frames,
            wall_seconds=wall_seconds,
        ),
        provenance=bundle.provenance,
    )


def _materialize_bundle(run_dir: Path, bundle: _ReplayBundle) -> None:
    run_dir.mkdir(parents=True, exist_ok=False)
    for rel_path in sorted(bundle.files):
        destination = run_dir / Path(*PurePosixPath(rel_path).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(bundle.files[rel_path])


def _remove_partial_output(target: Path, pre_existing: bool) -> None:
    if not pre_existing:
        shutil.rmtree(target, ignore_errors=True)
        return
    run_dir = target / _RUN_DIR_NAME
    if run_dir.is_dir():
        shutil.rmtree(run_dir, ignore_errors=True)
    for name in (_REPORT_NAME, _TRACE_NAME):
        try:
            (target / name).unlink()
        except OSError:
            pass
