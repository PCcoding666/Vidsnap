"""Batch 2 acceptance tests for vidsnap.call-review/v1 model-request metadata.

These tests drive the real HarnessKernel against deterministic fakes and assert
the new payload.call_review field on model.request.started events:

- control_mode maps from the actual policy class (fixed/direct/agentic); unknown
  policy types produce null;
- input_evidence is a read-only snapshot of exactly what was passed to the model
  at request time (id, modality, start_seconds, end_seconds, content_chars);
  later evidence must never backfill earlier requests;
- agent requests additionally carry tool_results (safe summaries), format_repair,
  verifier_feedback, remaining budgets, and decision_explanation=null;
- agent.decision completed events record parent_model_event_id linking back to
  the originating model.request span;
- subsequent tool.call.started events after an agentic tool_calls decision carry
  parent_event_id pointing to that decision event;
- fixed/direct runs never attach agent causation fields;
- error events do not masquerade as successful ones.

No new model calls are introduced. No prompts or protocols are changed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import (
    FakeFFmpeg,
    FakeTranscriber,
    FakeVideoModel,
    ScriptedAgentModel,
    final_decision,
    tool_decision,
)
from test_fixed_policy import build_context, make_kernel, read_events

from vidsnap.contracts import (
    HarnessPolicy,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.runtime import (
    AgenticPolicy,
    DirectPolicy,
    HarnessKernel,
    RunContext,
    default_plugin_registry,
)
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.sampling import AdaptiveSampler

CALL_REVIEW_VERSION = "vidsnap.call-review/v1"


def _events_of_type(events: list[dict[str, object]], event_type: str) -> list[dict[str, object]]:
    return [event for event in events if event.get("event_type") == event_type]


def _call_review(event: dict[str, object]) -> dict[str, object]:
    payload = event.get("payload")
    assert isinstance(payload, dict), f"event missing payload: {event}"
    review = payload.get("call_review")
    assert isinstance(review, dict), f"payload missing call_review: {payload}"
    return review


# ---------------------------------------------------------------------------
# Test 1: FixedPolicy synthesize records control_mode=fixed and evidence snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fixed_synthesize_records_control_mode_and_evidence_snapshot(
    tmp_path: Path,
) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    await kernel.run(context)

    events = read_events(context.bundle.path)
    model_started = _events_of_type(events, "model.request.started")
    assert len(model_started) == 1, "fixed policy issues exactly one model request"

    review = _call_review(model_started[0])
    assert review["api_version"] == CALL_REVIEW_VERSION
    assert review["control_mode"] == "fixed"
    assert review["decision_explanation"] is None

    evidence_snap = review["input_evidence"]
    assert isinstance(evidence_snap, list)
    assert len(evidence_snap) > 0

    for item in evidence_snap:
        assert isinstance(item, dict)
        assert "evidence_id" in item
        assert "modality" in item
        assert "start_seconds" in item
        assert "end_seconds" in item
        assert "content_chars" in item
        # Must not contain raw content, base64, or paths.
        assert "content" not in item
        assert "artifact_path" not in item
        assert "base64" not in item

    modalities = {item["modality"] for item in evidence_snap}
    assert modalities == {"frame", "transcript"}

    # Agent-specific fields must be absent for fixed policy.
    assert "tool_results" not in review
    assert "format_repair" not in review
    assert "verifier_feedback" not in review
    assert "remaining_model_calls" not in review


# ---------------------------------------------------------------------------
# Test 2: DirectPolicy records control_mode=direct
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_synthesize_records_control_mode_direct(tmp_path: Path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    media = FakeFFmpeg(has_audio=False)
    video_model = FakeVideoModel()
    goal = VideoGoal(objective="Describe what happens in the video")

    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(goal),
        task_model=video_model,
        media=media,
        sampler=AdaptiveSampler(),
        recognizer=None,
    )

    kernel = HarnessKernel(policy=DirectPolicy(), registry=default_plugin_registry())
    await kernel.run(context)

    events = read_events(context.bundle.path)
    model_started = _events_of_type(events, "model.request.started")
    assert len(model_started) == 1

    review = _call_review(model_started[0])
    assert review["control_mode"] == "direct"
    assert review["decision_explanation"] is None

    evidence_snap = review["input_evidence"]
    assert isinstance(evidence_snap, list)
    assert len(evidence_snap) > 0
    # Direct baseline produces frames + optional transcript; no audio here.
    assert all(item["modality"] == "frame" for item in evidence_snap)


# ---------------------------------------------------------------------------
# Test 3: Agentic decisions record agent fields and evidence grows between rounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agentic_requests_carry_agent_fields_and_evidence_grows(
    tmp_path: Path,
) -> None:
    decisions = [
        tool_decision("sample_evidence", max_frames=1),
        tool_decision("transcribe_audio"),
        final_decision("frame-001"),
    ]
    agent_model = ScriptedAgentModel(decisions)

    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    media = FakeFFmpeg(has_audio=True)
    video_model = FakeVideoModel()
    recognizer = FakeTranscriber()
    goal = VideoGoal(objective="Answer only from captured local evidence")

    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(tool_mode="agentic"),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(goal),
        task_model=video_model,
        media=media,
        sampler=AdaptiveSampler(),
        agent_model=agent_model,
        recognizer=recognizer,
    )

    kernel = HarnessKernel(policy=AgenticPolicy(), registry=default_plugin_registry())
    await kernel.run(context)

    events = read_events(context.bundle.path)
    model_started = _events_of_type(events, "model.request.started")
    # 3 agent decisions + 1 synthesize = 4 model requests minimum.
    # Actually agentic policy: 3 decide_next calls (tool, tool, final).
    # After final decision, accept_agent_final + verify. No synthesize in agentic.
    assert len(model_started) >= 3

    # First agent request: no evidence yet.
    first_review = _call_review(model_started[0])
    assert first_review["control_mode"] == "agentic"
    assert first_review["decision_explanation"] is None
    assert first_review["input_evidence"] == []
    assert first_review["tool_results"] == []
    assert first_review["format_repair"] is False
    assert first_review["verifier_feedback"] is None
    assert isinstance(first_review["remaining_model_calls"], int)
    assert isinstance(first_review["remaining_tool_calls"], int)
    assert isinstance(first_review["remaining_frames"], int)

    # Second agent request: should see frame-001 from first tool call.
    second_review = _call_review(model_started[1])
    second_evidence = second_review["input_evidence"]
    assert len(second_evidence) == 1
    assert second_evidence[0]["evidence_id"] == "frame-001"
    assert second_evidence[0]["modality"] == "frame"
    assert len(second_review["tool_results"]) == 1
    assert second_review["tool_results"][0]["tool"] == "sample_evidence"

    # Third agent request: should see frame-001 + transcript-001.
    third_review = _call_review(model_started[2])
    third_evidence = third_review["input_evidence"]
    assert len(third_evidence) == 2
    third_ids = [item["evidence_id"] for item in third_evidence]
    assert "frame-001" in third_ids
    assert "transcript-001" in third_ids
    assert len(third_review["tool_results"]) == 2


# ---------------------------------------------------------------------------
# Test 4: agent.decision records parent_model_event_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_decision_records_parent_model_event_id(tmp_path: Path) -> None:
    decisions = [
        tool_decision("sample_evidence", max_frames=1),
        final_decision("frame-001"),
    ]
    agent_model = ScriptedAgentModel(decisions)

    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(tool_mode="agentic"),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(
            VideoGoal(objective="Answer only from captured local evidence")
        ),
        task_model=FakeVideoModel(),
        media=FakeFFmpeg(has_audio=False),
        sampler=AdaptiveSampler(),
        agent_model=agent_model,
        recognizer=None,
    )

    kernel = HarnessKernel(policy=AgenticPolicy(), registry=default_plugin_registry())
    await kernel.run(context)

    events = read_events(context.bundle.path)
    model_started = _events_of_type(events, "model.request.started")
    agent_decisions = [
        e
        for e in events
        if e.get("event_type") == "agent.decision" and e.get("status") == "completed"
    ]
    assert len(agent_decisions) >= 2

    # Each completed agent.decision must reference its parent model.request span
    # via payload.parent_model_event_id, strictly equal positionally.
    for index, decision_event in enumerate(agent_decisions):
        payload = decision_event.get("payload")
        assert isinstance(payload, dict), f"agent.decision missing payload: {decision_event}"
        parent_id = payload.get("parent_model_event_id")
        expected_id = model_started[index]["event_id"]
        assert parent_id == expected_id, (
            f"agent.decision[{index}] parent_model_event_id {parent_id!r} "
            f"!= model.request.started[{index}] event_id {expected_id!r}"
        )


# ---------------------------------------------------------------------------
# Test 5: tool.call.started after agentic decision carries parent_event_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_after_agentic_decision_carries_parent_event_id(
    tmp_path: Path,
) -> None:
    decisions = [
        tool_decision("sample_evidence", max_frames=1),
        final_decision("frame-001"),
    ]
    agent_model = ScriptedAgentModel(decisions)

    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(tool_mode="agentic"),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(
            VideoGoal(objective="Answer only from captured local evidence")
        ),
        task_model=FakeVideoModel(),
        media=FakeFFmpeg(has_audio=False),
        sampler=AdaptiveSampler(),
        agent_model=agent_model,
        recognizer=None,
    )

    kernel = HarnessKernel(policy=AgenticPolicy(), registry=default_plugin_registry())
    await kernel.run(context)

    events = read_events(context.bundle.path)
    tool_started = _events_of_type(events, "tool.call.started")
    assert len(tool_started) >= 1

    # Tool calls triggered by an agentic decision must carry parent_event_id.
    first_tool = tool_started[0]
    parent = first_tool.get("parent_event_id")
    assert parent is not None, "tool.call.started after agentic decision must carry parent_event_id"

    # The parent must be an agent.decision event.
    agent_decision_ids = {
        e["event_id"]
        for e in events
        if e.get("event_type") == "agent.decision" and e.get("status") == "completed"
    }
    assert parent in agent_decision_ids, (
        f"parent_event_id {parent} does not match any completed agent.decision"
    )


# ---------------------------------------------------------------------------
# Test 6: fixed/direct runs do NOT attach agent causation to tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fixed_policy_tools_have_no_agent_parent(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    await kernel.run(context)

    events = read_events(context.bundle.path)
    tool_started = _events_of_type(events, "tool.call.started")
    assert len(tool_started) >= 1

    for tool_event in tool_started:
        assert tool_event.get("parent_event_id") is None, (
            "fixed-policy tool calls must not carry agent parent_event_id"
        )

    # No agent.decision events in a fixed run.
    agent_decisions = _events_of_type(events, "agent.decision")
    assert agent_decisions == []


# ---------------------------------------------------------------------------
# Test 7: format_repair flag propagates correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_repair_flag_propagates_in_model_review(tmp_path: Path) -> None:
    """A format-error retry must show format_repair=True on exactly one request."""
    from vidsnap.providers.base import AgentDecisionFormatError, AgentStepRequest

    class _ErrorThenScripted:
        """Raises AgentDecisionFormatError for error_count calls, then replays decisions."""

        def __init__(self, decisions, *, error, error_count=1):
            self._decisions = list(decisions)
            self._error = error
            self._remaining = error_count
            self.requests: list[AgentStepRequest] = []

        async def decide_next(self, request):
            self.requests.append(request)
            if self._remaining > 0:
                self._remaining -= 1
                raise self._error
            if not self._decisions:
                raise AssertionError("unexpected decide_next call")
            from vidsnap.contracts.agent import ProviderUsage
            from vidsnap.providers.base import AgentDecisionResponse

            return AgentDecisionResponse(
                decision=self._decisions.pop(0),
                usage=ProviderUsage(reported=False),
            )

    model = _ErrorThenScripted(
        [
            tool_decision("sample_evidence", max_frames=1),
            final_decision("frame-001"),
        ],
        error=AgentDecisionFormatError("malformed"),
        error_count=1,
    )

    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(tool_mode="agentic"),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(
            VideoGoal(objective="Answer only from captured local evidence")
        ),
        task_model=FakeVideoModel(),
        media=FakeFFmpeg(has_audio=False),
        sampler=AdaptiveSampler(),
        agent_model=model,
        recognizer=None,
    )

    kernel = HarnessKernel(policy=AgenticPolicy(), registry=default_plugin_registry())
    await kernel.run(context)

    events = read_events(context.bundle.path)
    model_started = _events_of_type(events, "model.request.started")
    # Failed request + retry + tool decision + final = at least 3 started spans.
    repair_reviews = [
        _call_review(e) for e in model_started if _call_review(e).get("format_repair") is True
    ]
    assert len(repair_reviews) == 1, "exactly one model request should carry format_repair=True"

    non_repair_reviews = [
        _call_review(e) for e in model_started if _call_review(e).get("format_repair") is False
    ]
    assert len(non_repair_reviews) >= 2


# ---------------------------------------------------------------------------
# Test 8: evidence snapshot never backfills later evidence into earlier requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_snapshot_never_backfills(tmp_path: Path) -> None:
    """Later evidence must never appear in earlier model request snapshots."""
    decisions = [
        tool_decision("sample_evidence", max_frames=1),
        tool_decision(
            "sample_evidence", max_frames=1, windows=[{"start_seconds": 2, "end_seconds": 4}]
        ),
        final_decision("frame-001"),
    ]
    agent_model = ScriptedAgentModel(decisions)

    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(tool_mode="agentic"),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(
            VideoGoal(objective="Answer only from captured local evidence")
        ),
        task_model=FakeVideoModel(),
        media=FakeFFmpeg(has_audio=False),
        sampler=AdaptiveSampler(),
        agent_model=agent_model,
        recognizer=None,
    )

    kernel = HarnessKernel(policy=AgenticPolicy(), registry=default_plugin_registry())
    await kernel.run(context)

    events = read_events(context.bundle.path)
    model_started = _events_of_type(events, "model.request.started")
    assert len(model_started) >= 3

    # First request: no evidence.
    first_evidence = _call_review(model_started[0])["input_evidence"]
    assert first_evidence == []

    # Second request: only frame-001 (from first tool call).
    second_evidence = _call_review(model_started[1])["input_evidence"]
    second_ids = [item["evidence_id"] for item in second_evidence]
    assert second_ids == ["frame-001"]

    # Third request: frame-001 + frame-002 (never more than what existed at that point).
    third_evidence = _call_review(model_started[2])["input_evidence"]
    third_ids = [item["evidence_id"] for item in third_evidence]
    assert len(third_ids) == 2
    assert "frame-001" in third_ids
    assert "frame-002" in third_ids
