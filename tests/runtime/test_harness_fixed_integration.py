"""Public VideoHarness fixed-policy integration through the bounded kernel.

This test drives the public VideoHarness.run with tool_mode=fixed against the
offline fakes and specifies the kernel-backed slice: the unchanged public
HarnessRunResult/VerificationReport/VideoAnalysisResult surface, a truthful
SUCCEEDED termination, a persisted result.json, zero planner or agent-model
calls, and the typed run/probe/tool.call/model.request/verifier events that the
legacy fixed path does not emit yet.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fakes import FakeFFmpeg, FakeTranscriber, FakeVideoModel, LegacyFakeRecognizer

from vidsnap.contracts import (
    HarnessPolicy,
    TerminalState,
    VideoAnalysisResult,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.harness import HarnessRunResult, VideoHarness
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.verifier import VerificationReport
from vidsnap.providers.base import ToolPlanResponse
from vidsnap.runtime import FixedPolicy, HarnessKernel, RunContext, default_plugin_registry
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.sampling import AdaptiveSampler


class SpyPlanner:
    """Records planner and agent-model invocations a fixed run must never make."""

    def __init__(self) -> None:
        self.plan_tools_calls = 0
        self.decide_next_calls = 0

    async def plan_tools(self, probe, goal) -> ToolPlanResponse:
        del probe, goal
        self.plan_tools_calls += 1
        raise AssertionError("fixed mode must not request an agentic tool plan")

    async def decide_next(self, request) -> object:
        del request
        self.decide_next_calls += 1
        raise AssertionError("fixed mode must not request an agent decision")


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


@pytest.mark.asyncio
async def test_public_fixed_run_uses_kernel_events_and_public_result_surface(tmp_path) -> None:
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    media = FakeFFmpeg(has_audio=True)
    model = FakeVideoModel()
    recognizer = LegacyFakeRecognizer()
    planner = SpyPlanner()
    run_dir = tmp_path / "run"

    result = await VideoHarness(
        media=media,
        model=model,
        recognizer=recognizer,
        planner=planner,
    ).run(
        VideoSource(path=source_path),
        VideoGoal(objective="Describe what happens in the video"),
        HarnessPolicy(tool_mode="fixed", output_dir=run_dir),
    )

    assert isinstance(result, HarnessRunResult)
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.failure_reason is None
    assert result.run_path == run_dir

    assert isinstance(result.result, VideoAnalysisResult)
    assert result.result.claims, "expected grounded claims in the public result"
    persisted = VideoAnalysisResult.model_validate_json((run_dir / "result.json").read_text())
    assert persisted == result.result

    assert isinstance(result.verification, VerificationReport)
    assert result.verification.passed is True
    assert result.verification.failed_gates == ()

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["terminal_state"] == "SUCCEEDED"
    assert manifest["finalized_at"] is not None
    result_bytes = (run_dir / "result.json").read_bytes()
    assert "result.json" in manifest["files"], (
        "result.json must be written before finalization so the manifest hashes it"
    )
    assert manifest["files"]["result.json"] == {
        "sha256": hashlib.sha256(result_bytes).hexdigest(),
        "bytes": len(result_bytes),
    }

    assert planner.plan_tools_calls == 0
    assert planner.decide_next_calls == 0
    assert model.analyze_calls == 1
    assert recognizer.calls, "fixed mode must transcribe audio-bearing media via the adapter"

    events = read_events(run_dir)
    event_types = [event.get("event_type") for event in events]
    assert "run.started" in event_types
    assert "probe.started" in event_types
    assert event_types.count("tool.call.started") >= 2
    assert "model.request.started" in event_types
    verifier_events = [event for event in events if event.get("event_type") == "verifier.completed"]
    assert verifier_events, "expected an approved verifier.completed event"
    assert verifier_events[0]["payload"]["passed"] is True
    terminal_events = [event for event in events if event.get("phase") == "terminal"]
    assert len(terminal_events) == 1


@pytest.mark.asyncio
async def test_public_fixed_run_relative_output_dir_preserves_legacy_run_path(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    relative_dir = Path("relative-run")

    result = await VideoHarness(
        media=FakeFFmpeg(has_audio=True),
        model=FakeVideoModel(),
        recognizer=LegacyFakeRecognizer(),
        planner=SpyPlanner(),
    ).run(
        VideoSource(path=source_path),
        VideoGoal(objective="Describe what happens in the video"),
        HarnessPolicy(tool_mode="fixed", output_dir=relative_dir),
    )

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.run_path == relative_dir, (
        "public run_path must stay the originally selected path, like the legacy loop"
    )
    assert not result.run_path.is_absolute()
    assert (relative_dir / "result.json").is_file()
    assert (relative_dir / "manifest.json").is_file()
    assert (relative_dir / "events.jsonl").is_file()


@pytest.mark.asyncio
async def test_kernel_result_writer_failure_yields_failed_and_still_finalizes(tmp_path) -> None:
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )

    def failing_writer(output: VideoAnalysisResult) -> Path:
        del output
        raise OSError("simulated result persistence failure")

    context: RunContext[VideoAnalysisResult, object] = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(
            VideoGoal(objective="Describe what happens in the video")
        ),
        task_model=FakeVideoModel(),
        media=FakeFFmpeg(has_audio=True),
        sampler=AdaptiveSampler(),
        recognizer=FakeTranscriber(),
        result_writer=failing_writer,
    )
    kernel: HarnessKernel[VideoAnalysisResult, object] = HarnessKernel(
        policy=FixedPolicy(),
        registry=default_plugin_registry(),
    )

    kernel_result = await kernel.run(context)

    assert kernel_result.terminal_state is TerminalState.FAILED
    assert kernel_result.failure_reason is not None
    manifest = json.loads((bundle.path / "manifest.json").read_text())
    assert manifest["terminal_state"] == "FAILED"
    assert manifest["finalized_at"] is not None, "a writer failure must still finalize the bundle"
    assert not (bundle.path / "result.json").exists()
