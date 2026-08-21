"""RunContext evidence accounting, redacted auditing, and artifact allocation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vidsnap.contracts import Evidence, HarnessPolicy, VideoGoal, VideoSource, default_loop_spec
from vidsnap.contracts.models import StrictModel
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder
from vidsnap.runtime import RunContext
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.sampling import AdaptiveSampler


class DummyModel:
    async def analyze_evidence(self, evidence, goal):  # type: ignore[no-untyped-def]
        raise AssertionError("RunContext must not call the model")


class DummyMedia:
    async def probe(self, source):  # type: ignore[no-untyped-def]
        raise AssertionError("RunContext must not call media")

    async def visual_candidates(self, source, probe):  # type: ignore[no-untyped-def]
        raise AssertionError("RunContext must not call media")

    async def extract_frames(self, source, candidates, output_dir):  # type: ignore[no-untyped-def]
        raise AssertionError("RunContext must not call media")

    async def extract_timeline_frames(self, source, *, fps, output_dir):  # type: ignore[no-untyped-def]
        raise AssertionError("RunContext must not call media")

    async def extract_audio(  # type: ignore[no-untyped-def]
        self, source, output_path, *, start_seconds=0.0, end_seconds=None
    ):
        raise AssertionError("RunContext must not call media")


class McqOutput(StrictModel):
    answer: str


class DummyTaskAdapter:
    goal = VideoGoal(objective="Answer the multiple choice question")
    output_model = McqOutput

    async def request_final(self, model, evidence, probe):  # type: ignore[no-untyped-def]
        raise AssertionError("RunContext must not call the adapter")

    def parse_final(self, payload):  # type: ignore[no-untyped-def]
        return McqOutput.model_validate(payload)

    def verify(self, output, evidence, probe):  # type: ignore[no-untyped-def]
        raise AssertionError("RunContext must not call the adapter")


def make_context(tmp_path: Path) -> RunContext:
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    goal = VideoGoal(objective="Summarize the video")
    return RunContext(
        source=VideoSource(path=tmp_path / "input.mp4"),
        policy=HarnessPolicy(),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(goal),
        task_model=DummyModel(),
        media=DummyMedia(),
        sampler=AdaptiveSampler(),
    )


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


def evidence_events(run_path: Path) -> list[dict[str, object]]:
    return [event for event in read_events(run_path) if event.get("phase") == "evidence.added"]


def test_next_id_allocates_stable_sequential_ids_per_modality(tmp_path) -> None:
    context = make_context(tmp_path)
    assert context.next_id("frame") == "frame-001"
    assert context.next_id("frame") == "frame-002"
    assert context.next_id("transcript") == "transcript-001"
    assert context.next_id("frame") == "frame-003"
    assert context.next_id("transcript") == "transcript-002"


def test_context_is_generic_over_output_and_task_model(tmp_path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    context: RunContext[McqOutput, DummyModel] = RunContext(
        source=VideoSource(path=tmp_path / "input.mp4"),
        policy=HarnessPolicy(),
        bundle=bundle,
        task_adapter=DummyTaskAdapter(),
        task_model=DummyModel(),
        media=DummyMedia(),
        sampler=AdaptiveSampler(),
    )

    assert context.output is None
    context.output = McqOutput(answer="B")
    assert context.output.answer == "B"


def test_context_requires_media_field(tmp_path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    goal = VideoGoal(objective="Summarize the video")

    with pytest.raises(TypeError):
        RunContext(
            source=VideoSource(path=tmp_path / "input.mp4"),
            policy=HarnessPolicy(),
            bundle=bundle,
            task_adapter=VideoAnalysisTaskAdapter(goal),
            task_model=DummyModel(),
            sampler=AdaptiveSampler(),
        )


def test_context_exposes_trace_recorder_bound_to_bundle(tmp_path) -> None:
    context = make_context(tmp_path)

    assert isinstance(context.trace, TraceRecorder)
    span = context.trace.start("tool", phase="tool.executed")
    context.trace.finish(span, status="completed")

    events = read_events(context.bundle.path)
    assert [event["event_type"] for event in events] == ["tool.started", "tool.completed"]


def test_add_persists_evidence_and_appends_redacted_event(tmp_path) -> None:
    context = make_context(tmp_path)
    evidence_id = context.next_id("transcript")
    secret_text = "top-secret transcript payload"
    evidence = Evidence(
        id=evidence_id,
        start_seconds=1.0,
        end_seconds=2.5,
        modality="transcript",
        content=secret_text,
        captured_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )

    assert context.add(evidence) == evidence_id

    stored = json.loads((context.bundle.path / "evidence" / f"{evidence_id}.json").read_text())
    assert stored["id"] == evidence_id
    assert stored["content"] == secret_text
    assert context.evidence == [evidence]

    events = evidence_events(context.bundle.path)
    assert len(events) == 1
    payload = events[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["evidence_id"] == evidence_id
    assert payload["modality"] == "transcript"
    assert payload["start_seconds"] == 1.0
    assert payload["end_seconds"] == 2.5
    assert payload["captured_at"] == "2026-08-21T00:00:00Z"
    raw_events = (context.bundle.path / "events.jsonl").read_text()
    assert secret_text not in raw_events
    assert "data:" not in raw_events
    assert "content" not in payload


def test_add_emits_typed_completed_event_with_event_id(tmp_path) -> None:
    context = make_context(tmp_path)
    evidence_id = context.next_id("frame")
    evidence = Evidence(id=evidence_id, start_seconds=0.0, end_seconds=1.0, modality="frame")

    context.add(evidence)

    event = evidence_events(context.bundle.path)[0]
    assert event["event_type"] == "evidence.added"
    assert event["status"] == "completed"
    assert isinstance(event["event_id"], str)
    assert event["event_id"]


def test_add_records_artifact_byte_metadata(tmp_path) -> None:
    context = make_context(tmp_path)
    artifact = context.bundle.path / "artifacts" / "call-001" / "frame.jpg"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"x" * 128)
    evidence_id = context.next_id("frame")
    evidence = Evidence(
        id=evidence_id,
        start_seconds=0.0,
        end_seconds=0.0,
        modality="frame",
        artifact_path=artifact,
    )

    context.add(evidence)

    payload = evidence_events(context.bundle.path)[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["artifact_bytes"] == 128


def test_add_rejects_artifact_outside_bundle_artifacts(tmp_path) -> None:
    context = make_context(tmp_path)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"x" * 8)
    evidence_id = context.next_id("frame")
    evidence = Evidence(
        id=evidence_id,
        start_seconds=0.0,
        end_seconds=0.0,
        modality="frame",
        artifact_path=outside,
    )

    with pytest.raises(ValueError, match="artifact"):
        context.add(evidence)

    assert context.evidence == []
    assert not (context.bundle.path / "evidence" / f"{evidence_id}.json").exists()
    assert evidence_events(context.bundle.path) == []


def test_add_rejects_missing_artifact(tmp_path) -> None:
    context = make_context(tmp_path)
    missing = context.bundle.path / "artifacts" / "call-001" / "frame.jpg"
    evidence_id = context.next_id("frame")
    evidence = Evidence(
        id=evidence_id,
        start_seconds=0.0,
        end_seconds=0.0,
        modality="frame",
        artifact_path=missing,
    )

    with pytest.raises(ValueError, match="artifact"):
        context.add(evidence)

    assert context.evidence == []
    assert not (context.bundle.path / "evidence" / f"{evidence_id}.json").exists()
    assert evidence_events(context.bundle.path) == []


def test_add_rejects_evidence_without_allocated_id(tmp_path) -> None:
    context = make_context(tmp_path)
    rogue = Evidence(id="frame-999", start_seconds=0.0, end_seconds=1.0, modality="frame")

    with pytest.raises(ValueError, match="not allocated"):
        context.add(rogue)

    assert context.evidence == []
    assert not (context.bundle.path / "evidence" / "frame-999.json").exists()
    assert evidence_events(context.bundle.path) == []


def test_add_rejects_duplicate_evidence_id(tmp_path) -> None:
    context = make_context(tmp_path)
    evidence_id = context.next_id("frame")
    first = Evidence(id=evidence_id, start_seconds=0.0, end_seconds=1.0, modality="frame")
    context.add(first)

    with pytest.raises(ValueError, match="already"):
        context.add(first.model_copy())

    assert context.evidence == [first]
    assert len(evidence_events(context.bundle.path)) == 1


def test_next_artifact_dir_is_unique_per_sequential_call(tmp_path) -> None:
    context = make_context(tmp_path)
    first = context.next_artifact_dir()
    second = context.next_artifact_dir()
    third = context.next_artifact_dir()

    assert len({first, second, third}) == 3
    for directory in (first, second, third):
        assert directory.is_dir()
        assert directory.parent == context.bundle.path / "artifacts"


def test_context_starts_with_empty_accounting_state(tmp_path) -> None:
    context = make_context(tmp_path)
    assert context.evidence == []
    assert context.output is None
    assert context.verification is None
    assert context.terminal_state is None
    assert context.probe is None
    assert context.agent_model is None
    assert context.recognizer is None
    assert context.tool_result_summaries == []
    assert context.verifier_feedback is None
    assert context.call_fingerprints == set()
    assert context.format_repair_used is False
    assert context.model_calls == 0
    assert context.tool_calls == 0
    assert context.iterations == 0
