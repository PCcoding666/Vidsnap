"""FixedPolicy driven end-to-end through HarnessKernel against deterministic fakes.

These tests specify the bounded, non-agentic run: a fixed phase sequence, no
decide_next calls, truthful SUCCEEDED termination, persisted frame and transcript
evidence, balanced started/terminal trace events, and ASR skipped for silent media.

They are written RED-first: they import HarnessKernel, FixedPolicy, and
default_plugin_registry from vidsnap.runtime, which do not exist yet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fakes import FakeAgentModel, FakeFFmpeg, FakeTranscriber, FakeVideoModel

from vidsnap.contracts import (
    HarnessPolicy,
    TerminalState,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.runtime import FixedPolicy, HarnessKernel, RunContext, default_plugin_registry
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.sampling import AdaptiveSampler

EXPECTED_PHASES = [
    "probe_media",
    "transcribe_audio",
    "sample_evidence",
    "synthesize_result",
    "verify_claims",
    "terminal",
]

TRACE_BASE_TYPES = {"run", "model", "tool"}
TERMINAL_STATUSES = {"completed", "failed", "blocked", "skipped"}


def build_context(tmp_path: Path, *, has_audio: bool):
    """Assemble a generic RunContext wired to deterministic fakes and a real RunBundle."""
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    media = FakeFFmpeg(has_audio=has_audio)
    recognizer = FakeTranscriber()
    video_model = FakeVideoModel()
    agent_model = FakeAgentModel()
    goal = VideoGoal(objective="Describe what happens in the video")

    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(goal),
        task_model=video_model,
        media=media,
        sampler=AdaptiveSampler(),
        agent_model=agent_model,
        recognizer=recognizer,
    )
    return context, media, video_model, agent_model, recognizer


def make_kernel() -> HarnessKernel:
    return HarnessKernel(policy=FixedPolicy(), registry=default_plugin_registry())


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


def completed_phases(events: list[dict[str, object]]) -> list[object]:
    """Ordered top-level phase markers emitted by the kernel as phase spans."""
    return [event["phase"] for event in events if event.get("event_type") == "phase.completed"]


def trace_started_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    started = []
    for event in events:
        event_type = event.get("event_type")
        if not isinstance(event_type, str) or not event_type.endswith(".started"):
            continue
        if event_type.split(".", 1)[0] in TRACE_BASE_TYPES:
            started.append(event)
    return started


def terminal_events_for(
    events: list[dict[str, object]], correlation_id: object
) -> list[dict[str, object]]:
    return [
        event
        for event in events
        if event.get("correlation_id") == correlation_id
        and event.get("status") in TERMINAL_STATUSES
    ]


def assert_started_spans_are_balanced(events: list[dict[str, object]]) -> None:
    """Every run/model/tool started event has exactly one same-correlation terminal event."""
    started = trace_started_events(events)
    assert started, "expected at least one run/model/tool started trace event"
    for span in started:
        correlation_id = span.get("correlation_id")
        assert correlation_id is not None, f"started span missing correlation_id: {span}"
        terminals = terminal_events_for(events, correlation_id)
        assert len(terminals) == 1, (
            f"started event {span.get('event_type')} correlation {correlation_id} "
            f"has {len(terminals)} terminal events, expected exactly one"
        )


@pytest.mark.asyncio
async def test_fixed_policy_runs_exact_phase_sequence_to_success(tmp_path) -> None:
    context, _media, video_model, agent_model, _recognizer = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    await kernel.run(context)

    events = read_events(context.bundle.path)
    assert completed_phases(events) == EXPECTED_PHASES
    assert agent_model.decide_next_calls == 0
    assert video_model.analyze_calls == 1
    assert context.terminal_state is TerminalState.SUCCEEDED

    frame_ids = [item.id for item in context.evidence if item.modality == "frame"]
    transcript_ids = [item.id for item in context.evidence if item.modality == "transcript"]
    assert frame_ids, "expected frame evidence to be captured"
    assert transcript_ids, "expected transcript evidence to be captured"
    for evidence_id in frame_ids + transcript_ids:
        assert (context.bundle.path / "evidence" / f"{evidence_id}.json").exists()

    assert_started_spans_are_balanced(events)


@pytest.mark.asyncio
async def test_fixed_policy_skips_asr_for_silent_media(tmp_path) -> None:
    context, media, _video_model, agent_model, recognizer = build_context(tmp_path, has_audio=False)
    kernel = make_kernel()

    await kernel.run(context)

    assert recognizer.calls == [], "silent media must not invoke the recognizer"
    assert media.audio_calls == [], "silent media must not extract audio"
    assert not [item for item in context.evidence if item.modality == "transcript"]
    assert [item for item in context.evidence if item.modality == "frame"]
    assert agent_model.decide_next_calls == 0

    events = read_events(context.bundle.path)
    assert_started_spans_are_balanced(events)
