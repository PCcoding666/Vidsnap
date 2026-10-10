"""Real RunBundle + TraceRecorder fixtures for studio projection tests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from vidsnap.contracts import TerminalState, default_loop_spec
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.models import Claim, Evidence, EvidenceReference, VideoAnalysisResult
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder

PROVIDER_URL = "https://leak-key@studio-provider.internal/v1?api_key=leaky-query"
EVIDENCE_MARKER = "STUDIO_EVIDENCE_MARKER_9f3c"
CLAIM_MARKER = "STUDIO_CLAIM_MARKER_4b7d"
VIDEO_SHA256 = "a" * 64

FULL_CLOCK = (0.0, 0.12, 0.2, 0.31, 0.4, 0.45)


def build_trial_bundle(
    root: Path,
    relative_run: str,
    *,
    with_usage: bool = True,
    usage_reported: bool = True,
    finish_run: bool = True,
    verify: tuple[bool, Sequence[str]] | None = None,
    tools: Sequence[str] = (),
    with_evidence: bool = False,
    with_result: bool = False,
    run_payload: dict[str, object] | None = None,
    clock_values: Sequence[float] = FULL_CLOCK,
) -> Path:
    """Create one finalized RunBundle with real paired trace events."""
    bundle = RunBundle.create(
        root / relative_run,
        loop_spec=default_loop_spec(),
        provider_url=PROVIDER_URL,
    )
    recorder = TraceRecorder(bundle, clock=iter(clock_values).__next__)
    run_span = recorder.start("run", phase="run", payload=run_payload)
    if with_usage:
        model_span = recorder.start("model.request", phase="agent_decision", turn=1, step=1)
        recorder.finish(
            model_span,
            status="completed",
            usage=ProviderUsage(input_tokens=7, output_tokens=3, reported=usage_reported),
        )
    for tool_name in tools:
        tool_span = recorder.start(
            "tool.call",
            phase=tool_name,
            turn=1,
            step=2,
            payload={"name": tool_name},
        )
        recorder.finish(tool_span, status="completed", payload={"name": tool_name})
    if with_evidence:
        bundle.write_evidence(
            Evidence(
                id="ev-001",
                start_seconds=0.0,
                end_seconds=1.0,
                modality="frame",
                content=EVIDENCE_MARKER,
            )
        )
    if with_result:
        bundle.write_result(
            VideoAnalysisResult(
                summary="studio summary",
                claims=[
                    Claim(
                        text=CLAIM_MARKER,
                        evidence=[EvidenceReference(evidence_id="ev-001")],
                    )
                ],
            )
        )
    if verify is not None:
        passed, failed_gates = verify
        verify_span = recorder.start("verifier", phase="verify_claims")
        recorder.finish(
            verify_span,
            status="completed",
            payload={"passed": passed, "failed_gates": list(failed_gates)},
        )
    if finish_run:
        recorder.finish(run_span, status="completed", phase="terminal")
    bundle.finalize(TerminalState.SUCCEEDED)
    return bundle.path


def _studio_manifest_payload() -> dict[str, object]:
    return {
        "api_version": "vidsnap.studio/v1",
        "title": "Studio projection fixture",
        "iteration": {
            "agent_id": "video-summarizer",
            "versions": [
                {
                    "version": "v0",
                    "summary": "baseline prompt",
                    "prompt_sha256": "b" * 64,
                    "cases": [
                        {
                            "case_id": "case-01",
                            "video_sha256": VIDEO_SHA256,
                            "trials": [
                                {"trial_id": "t1", "run": "runs/v0/case-01/t1"},
                                {"trial_id": "t2", "run": "runs/v0/case-01/t2"},
                            ],
                        },
                        {
                            "case_id": "case-02",
                            "held_out": True,
                            "trials": [{"trial_id": "t1", "run": "runs/v0/case-02/t1"}],
                        },
                    ],
                },
                {
                    "version": "v1",
                    "summary": "tightened prompt",
                    "cases": [
                        {
                            "case_id": "case-01",
                            "video_sha256": VIDEO_SHA256,
                            "trials": [{"trial_id": "t1", "run": "runs/v1/case-01/t1"}],
                        }
                    ],
                },
            ],
        },
        "exploration": {
            "problem": {"statement": "explore a bounded task", "constraints": ["stay local"]},
            "approaches": [
                {
                    "id": "full-approach",
                    "label": "Fully recorded approach",
                    "harness": {"max_model_calls": 12, "max_tool_calls": 6},
                    "trials": [
                        {"trial_id": "t1", "run": "runs/exp/full/t1"},
                        {"trial_id": "t2", "run": "runs/exp/full/t2"},
                    ],
                },
                {
                    "id": "partial-approach",
                    "label": "Partially recorded approach",
                    "harness": {"max_model_calls": 12, "max_tool_calls": 6},
                    "trials": [
                        {"trial_id": "t1", "run": "runs/exp/partial/t1"},
                        {"trial_id": "t2", "run": "runs/exp/partial/t2"},
                    ],
                },
            ],
        },
    }


@pytest.fixture
def studio_root(tmp_path: Path) -> Path:
    """A manifest root with real iteration and exploration RunBundles."""
    root = tmp_path / "studio"
    build_trial_bundle(
        root,
        "runs/v0/case-01/t1",
        tools=("transcribe_audio",),
        clock_values=(0.0, 0.12, 0.2, 0.24, 0.28, 0.31, 0.4, 0.45),
        with_evidence=True,
        with_result=True,
        verify=(True, ()),
    )
    build_trial_bundle(root, "runs/v0/case-01/t2", with_usage=False, finish_run=False)
    build_trial_bundle(root, "runs/v0/case-02/t1", verify=(False, ("schema_valid",)))
    build_trial_bundle(
        root,
        "runs/v1/case-01/t1",
        tools=("sample_evidence",),
        clock_values=(0.0, 0.12, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45),
        verify=(True, ()),
    )
    build_trial_bundle(
        root,
        "runs/exp/full/t1",
        tools=("transcribe_audio", "sample_evidence"),
        clock_values=(0.0, 0.12, 0.2, 0.22, 0.26, 0.28, 0.32, 0.36, 0.4, 0.45),
        verify=(True, ()),
    )
    build_trial_bundle(
        root,
        "runs/exp/full/t2",
        tools=("sample_evidence", "transcribe_audio"),
        clock_values=(0.0, 0.12, 0.2, 0.22, 0.26, 0.28, 0.32, 0.36, 0.4, 0.45),
        verify=(False, ("claims_are_supported",)),
    )
    build_trial_bundle(root, "runs/exp/partial/t1", verify=(True, ()))
    build_trial_bundle(root, "runs/exp/partial/t2", with_usage=False)
    root.mkdir(parents=True, exist_ok=True)
    (root / "studio.json").write_text(json.dumps(_studio_manifest_payload()), encoding="utf-8")
    return root


@pytest.fixture
def studio_manifest_path(studio_root: Path) -> Path:
    return studio_root / "studio.json"


@pytest.fixture
def claim_marker() -> str:
    return CLAIM_MARKER


@pytest.fixture
def evidence_marker() -> str:
    return EVIDENCE_MARKER


@pytest.fixture
def provider_url() -> str:
    return PROVIDER_URL


@pytest.fixture
def build_bundle():
    return build_trial_bundle
