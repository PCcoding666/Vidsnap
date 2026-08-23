"""RED tests for Task 9: DirectPolicy drives the fps=2 direct baseline through the kernel.

These tests specify the bounded, tool-free direct variant: probe once, extract the
complete fps=2 timeline exactly once, preserve every frame beyond the
model-selected evidence cap, mark every Evidence item budget_class="direct_baseline",
run exactly one MCQ model call with frame_sequence_fps=2 and the optional registered
subtitle, then verify and finalize SUCCEEDED with truthful events and manifest hashes.

They are written RED-first: they import DirectPolicy from vidsnap.runtime and assert
Evidence.budget_class, neither of which exists yet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from fakes import FakeAgentModel, FakeFFmpeg, FakeTranscriber, FakeVideoModel

from vidsnap.benchmark.adapters import FormalTranscriptionAdapter, MCQTaskAdapter
from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import MCQModelResponse
from vidsnap.contracts import (
    Evidence,
    HarnessPolicy,
    TerminalState,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.runtime import (
    DirectPolicy,
    FixedPolicy,
    HarnessKernel,
    RunContext,
    default_plugin_registry,
)
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.probe import ExtractedFrame
from vidsnap.video.sampling import AdaptiveSampler

VIDEO_SECONDS = 60.0
TIMELINE_FPS = 2
EXPECTED_FRAMES = int(VIDEO_SECONDS * TIMELINE_FPS)  # 120 frames, far above the cap
FRAME_CAP = 10
SUBTITLE_TEXT = "registered subtitle"

_TRACE_BASE_TYPES = {"run", "probe", "model"}
_TERMINAL_STATUSES = {"completed", "failed", "blocked", "skipped"}


class TimelineRecordingFFmpeg(FakeFFmpeg):
    """FakeFFmpeg that also records every extract_timeline_frames fps argument."""

    def __init__(self, *, has_audio: bool = True, duration_seconds: float = VIDEO_SECONDS):
        super().__init__(has_audio=has_audio, duration_seconds=duration_seconds)
        self.timeline_fps: list[int] = []

    async def extract_timeline_frames(
        self,
        source: Path,
        *,
        fps: int,
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        self.timeline_fps.append(fps)
        return await super().extract_timeline_frames(source, fps=fps, output_dir=output_dir)


class RecordingMCQModel:
    """A fake formal MCQ model that captures every input and reports real counters."""

    def __init__(self, *, answer_text: str = "The best answer is: A.") -> None:
        self.answer_text = answer_text
        self.answer_calls: list[dict[str, object]] = []
        self.transcribe_calls: list[bytes] = []

    async def answer_mcq(
        self,
        case: FormalCase,
        *,
        frames: tuple[ExtractedFrame, ...],
        transcript: str | None,
        video_path: Path | None,
        frame_sequence_fps: int | None = None,
    ) -> MCQModelResponse:
        self.answer_calls.append(
            {
                "case": case,
                "frames": frames,
                "transcript": transcript,
                "video_path": video_path,
                "frame_sequence_fps": frame_sequence_fps,
            }
        )
        return MCQModelResponse(
            self.answer_text,
            input_tokens=13,
            output_tokens=1,
            input_bytes=100,
            usage_reported=True,
        )

    async def transcribe_audio(self, audio_bytes: bytes) -> MCQModelResponse:
        self.transcribe_calls.append(audio_bytes)
        return MCQModelResponse(
            "spoken words",
            input_tokens=7,
            output_tokens=3,
            input_bytes=75,
            usage_reported=True,
        )


def make_case(tmp_path: Path, *, subtitle: bool) -> FormalCase:
    video = tmp_path / "input.mp4"
    video.write_bytes(b"deterministic-local-video-bytes")
    subtitle_path: Path | None = None
    if subtitle:
        subtitle_path = tmp_path / "subtitle.srt"
        subtitle_path.write_text(SUBTITLE_TEXT, encoding="utf-8")
    return FormalCase(
        case_id="case-direct",
        dataset="Video-MME",
        dataset_version="revision",
        dataset_license="Academic research only.",
        source_url="https://github.com/MME-Benchmarks/Video-MME",
        source=video,
        source_sha256="a" * 64,
        task_family="Information Synopsis",
        question="What happens in the video?",
        options={"A": "One event", "B": "Another event"},
        answer="A",
        subtitle_path=subtitle_path,
        has_audio=subtitle,
        duration_stratum="short",
        requirements=("visual",),
        expected_tools=("sample_evidence",),
        tool_annotation_reason="visual-required",
    )


def build_direct_context(
    tmp_path: Path,
    *,
    subtitle: bool,
):
    """Assemble one RunContext for a direct baseline run over a 60s fake video."""
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    case = make_case(tmp_path, subtitle=subtitle)
    media = TimelineRecordingFFmpeg(has_audio=subtitle)
    model = RecordingMCQModel()
    agent_model = FakeAgentModel()
    recognizer = (
        FormalTranscriptionAdapter(model, subtitle_text=SUBTITLE_TEXT) if subtitle else None
    )
    context: RunContext = RunContext(
        source=VideoSource(path=case.source),
        policy=HarnessPolicy(max_evidence_frames=FRAME_CAP),
        bundle=bundle,
        task_adapter=MCQTaskAdapter(case),
        task_model=model,
        media=media,
        sampler=AdaptiveSampler(),
        agent_model=agent_model,
        recognizer=recognizer,
    )
    return context, case, media, model, agent_model


def make_direct_kernel() -> HarnessKernel:
    return HarnessKernel(policy=DirectPolicy(), registry=default_plugin_registry())


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


def events_of_type(events: list[dict[str, object]], event_type: str) -> list[dict[str, object]]:
    return [event for event in events if event.get("event_type") == event_type]


def assert_started_spans_are_balanced(events: list[dict[str, object]]) -> None:
    """Every run/probe/model started event has one same-correlation terminal event."""
    started = [
        event
        for event in events
        if isinstance(event.get("event_type"), str)
        and event["event_type"].endswith(".started")
        and event["event_type"].split(".", 1)[0] in _TRACE_BASE_TYPES
    ]
    assert started, "expected at least one run/probe/model started trace event"
    for span in started:
        correlation_id = span.get("correlation_id")
        assert correlation_id is not None, f"started span missing correlation_id: {span}"
        terminals = [
            event
            for event in events
            if event.get("correlation_id") == correlation_id
            and event.get("status") in _TERMINAL_STATUSES
        ]
        assert len(terminals) == 1, (
            f"started event {span.get('event_type')} correlation {correlation_id} "
            f"has {len(terminals)} terminal events, expected exactly one"
        )


def assert_manifest_hashes_are_truthful(run_path: Path, *, terminal_state: str) -> None:
    """The finalized manifest hashes every persisted file and records the terminal state."""
    manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["terminal_state"] == terminal_state
    files = manifest["files"]
    assert isinstance(files, dict) and "events.jsonl" in files
    for relative, digest in files.items():
        target = run_path / relative
        assert target.is_file(), f"manifest lists a missing file: {relative}"
        content = target.read_bytes()
        assert digest["sha256"] == hashlib.sha256(content).hexdigest()
        assert digest["bytes"] == len(content)
    evidence_files = {f"evidence/{path.name}" for path in (run_path / "evidence").iterdir()}
    assert evidence_files <= set(files), "every persisted evidence file must be hashed"


def assert_direct_baseline_events(
    events: list[dict[str, object]], *, evidence: Sequence[Evidence]
) -> None:
    """Run/model/evidence/budget events are truthful for a tool-free direct run."""
    assert events[0]["event_type"] == "run.started"
    assert events[-1]["event_type"] == "run.completed"

    tool_events = [
        event
        for event in events
        if isinstance(event.get("event_type"), str) and event["event_type"].startswith("tool.call")
    ]
    assert tool_events == [], "direct runs must emit no tool.call events"

    model_started = events_of_type(events, "model.request.started")
    assert len(model_started) == 1, "direct runs make exactly one model request"
    model_completed = events_of_type(events, "model.request.completed")
    assert len(model_completed) == 1
    assert model_completed[0].get("usage") is not None

    added = events_of_type(events, "evidence.added")
    assert [event["payload"]["evidence_id"] for event in added] == [item.id for item in evidence], (
        "every retained evidence item must be audited exactly once"
    )

    budgets = events_of_type(events, "budget.updated")
    assert budgets, "expected truthful budget.updated snapshots"
    final_budget = budgets[-1]["payload"]
    assert final_budget["tool_calls"] == 0
    assert final_budget["model_calls"] == 1
    assert final_budget["evidence_frames"] == EXPECTED_FRAMES

    assert_started_spans_are_balanced(events)


@pytest.mark.asyncio
async def test_direct_policy_preserves_complete_fps2_baseline_with_subtitle(tmp_path) -> None:
    context, case, media, model, agent_model = build_direct_context(tmp_path, subtitle=True)
    kernel = make_direct_kernel()

    result = await kernel.run(context)

    assert media.probe_calls == 1
    assert media.timeline_calls == 1
    assert media.timeline_fps == [TIMELINE_FPS]
    assert media.candidate_calls == 0, "direct must not run visual candidate selection"
    assert media.extracted_frame_calls == 0, "direct must not run candidate frame extraction"

    frames = [item for item in context.evidence if item.modality == "frame"]
    transcripts = [item for item in context.evidence if item.modality == "transcript"]
    assert len(frames) == EXPECTED_FRAMES, (
        f"direct baseline must preserve all {EXPECTED_FRAMES} fps=2 frames, "
        f"not truncate to the {FRAME_CAP}-frame model-selected cap"
    )
    assert [frame.start_seconds for frame in frames] == [
        index / TIMELINE_FPS for index in range(EXPECTED_FRAMES)
    ]
    assert len(transcripts) == 1
    assert transcripts[0].content == SUBTITLE_TEXT
    for item in context.evidence:
        assert item.budget_class == "direct_baseline"
        assert (context.bundle.path / "evidence" / f"{item.id}.json").exists()
    persisted_frame = json.loads(
        (context.bundle.path / "evidence" / f"{frames[0].id}.json").read_text(encoding="utf-8")
    )
    assert persisted_frame["budget_class"] == "direct_baseline"

    assert context.tool_calls == 0
    assert context.model_calls == 1
    assert agent_model.decide_next_calls == 0, "direct must never consult the agent model"

    assert len(model.answer_calls) == 1
    call = model.answer_calls[0]
    assert call["case"] is case
    assert call["frame_sequence_fps"] == TIMELINE_FPS
    call_frames = call["frames"]
    assert isinstance(call_frames, tuple) and len(call_frames) == EXPECTED_FRAMES
    assert call["transcript"] == SUBTITLE_TEXT
    assert call["video_path"] is None
    assert model.transcribe_calls == [], "a registered subtitle must not consume a model call"

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert context.terminal_state is TerminalState.SUCCEEDED
    assert result.output is not None and result.output.answer == case.answer
    assert result.verification is not None and result.verification.passed

    events = read_events(context.bundle.path)
    assert_direct_baseline_events(events, evidence=context.evidence)
    assert_manifest_hashes_are_truthful(context.bundle.path, terminal_state="SUCCEEDED")


@pytest.mark.asyncio
async def test_direct_policy_succeeds_without_registered_subtitle(tmp_path) -> None:
    context, _case, media, model, agent_model = build_direct_context(tmp_path, subtitle=False)
    kernel = make_direct_kernel()

    result = await kernel.run(context)

    assert media.timeline_calls == 1
    assert media.timeline_fps == [TIMELINE_FPS]
    frames = [item for item in context.evidence if item.modality == "frame"]
    assert len(frames) == EXPECTED_FRAMES
    assert all(item.budget_class == "direct_baseline" for item in context.evidence)
    assert not [item for item in context.evidence if item.modality == "transcript"]

    assert context.tool_calls == 0
    assert context.model_calls == 1
    assert agent_model.decide_next_calls == 0
    assert len(model.answer_calls) == 1
    call = model.answer_calls[0]
    assert call["frame_sequence_fps"] == TIMELINE_FPS
    assert isinstance(call["frames"], tuple) and len(call["frames"]) == EXPECTED_FRAMES
    assert call["transcript"] is None

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.verification is not None and result.verification.passed

    events = read_events(context.bundle.path)
    assert_direct_baseline_events(events, evidence=context.evidence)
    assert_manifest_hashes_are_truthful(context.bundle.path, terminal_state="SUCCEEDED")


@pytest.mark.asyncio
async def test_tool_plugin_frame_evidence_defaults_to_model_selected(tmp_path) -> None:
    """Contrast: frames acquired through tool plugins are model-selected, not baseline."""
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(VideoGoal(objective="Describe the video")),
        task_model=FakeVideoModel(),
        media=FakeFFmpeg(has_audio=True),
        sampler=AdaptiveSampler(),
        agent_model=FakeAgentModel(),
        recognizer=FakeTranscriber(),
    )
    kernel = HarnessKernel(policy=FixedPolicy(), registry=default_plugin_registry())

    await kernel.run(context)

    frames = [item for item in context.evidence if item.modality == "frame"]
    assert frames, "expected tool-plugin frame evidence"
    assert context.tool_calls > 0
    for item in frames:
        assert item.budget_class == "model_selected"
