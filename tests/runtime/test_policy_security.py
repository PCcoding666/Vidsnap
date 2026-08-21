"""RED security acceptance tests for the agentic kernel path.

These tests drive the public VideoHarness in agentic mode against deterministic
ScriptedAgentModel scripts and assert the security invariants the bounded kernel
must enforce, without modifying any production code:

- an agent decision naming an unknown tool (open_url) ends FAILED and executes
  no tool at all;
- an exact repeated paid sample_evidence call with canonical-equivalent
  arguments is rejected before a second execution, terminating the run FAILED
  with exactly one completed sample call (this slice is expected RED today);
- six unique valid tool calls may complete, but a seventh ends EXHAUSTED and
  never starts a span;
- invalid tool arguments are rejected before plugin execution, leaving no
  tool.call started or completed events.

Task 8 one-time agent-decision format repair (RED):

- a syntactically/schema-invalid agent decision body raises a dedicated
  AgentDecisionFormatError; the kernel grants exactly one retry whose
  AgentStepRequest carries format_repair=True, and a recovered run still
  succeeds with truthful events and a finalized manifest;
- two consecutive malformed decisions terminate FAILED after exactly two
  model calls, with only the second request marked format_repair=True;
- every failed malformed attempt leaves a paired failed model.request span and
  one agent.decision failed event whose payload never contains the raw body;
- ordinary ProviderError transport failures receive no format-repair retry.

Each test asserts the truthful finalized manifest state and, where applicable,
the paired tool.call span accounting.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from fakes import (
    FakeFFmpeg,
    FakeVideoModel,
    LegacyFakeRecognizer,
    ScriptedAgentModel,
    final_decision,
    tool_decision,
)

from vidsnap.contracts import HarnessPolicy, TerminalState, VideoGoal, VideoSource
from vidsnap.contracts.agent import AgentDecision
from vidsnap.harness import HarnessRunResult, VideoHarness
from vidsnap.providers.base import AgentDecisionResponse, AgentStepRequest, ProviderError

try:  # RED: Task 8 has not introduced this dedicated provider error yet.
    from vidsnap.providers.base import AgentDecisionFormatError
except ImportError:
    AgentDecisionFormatError = None  # type: ignore[assignment,misc]

TRANSCRIPT_TEXT = "legacy spoken content"


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


def events_of_type(events: list[dict[str, object]], event_type: str) -> list[dict[str, object]]:
    return [event for event in events if event.get("event_type") == event_type]


def completed_tool_names(events: list[dict[str, object]]) -> list[str]:
    """Ordered names of every tool call that really executed to completion."""
    return [
        str(event["payload"]["name"]) for event in events_of_type(events, "tool.call.completed")
    ]


def started_tool_names(events: list[dict[str, object]]) -> list[str]:
    """Ordered names of every tool call that ever opened an execution span."""
    return [str(event["payload"]["name"]) for event in events_of_type(events, "tool.call.started")]


def read_manifest(run_path: Path) -> dict[str, object]:
    return json.loads((run_path / "manifest.json").read_text())


async def run_scripted_agent(
    decisions: Sequence[AgentDecision], tmp_path: Path
) -> tuple[HarnessRunResult, ScriptedAgentModel, FakeFFmpeg]:
    """Run one public agentic harness invocation against a scripted agent model."""
    media = FakeFFmpeg(has_audio=True)
    model = ScriptedAgentModel(decisions)
    harness = VideoHarness(
        media=media,
        model=model,
        recognizer=LegacyFakeRecognizer(text=TRANSCRIPT_TEXT),
        planner=model,
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    result = await harness.run(
        VideoSource(path=source_path),
        VideoGoal(objective="Answer only from captured local evidence"),
        HarnessPolicy(tool_mode="agentic", output_dir=tmp_path / "run"),
    )
    return result, model, media


@pytest.mark.asyncio
async def test_unknown_tool_name_fails_without_executing_anything(tmp_path: Path) -> None:
    decisions = [tool_decision("open_url", url="https://evil.example/payload")]
    result, model, media = await run_scripted_agent(decisions, tmp_path)

    assert model.plan_tools_calls == 0
    assert result.terminal_state is TerminalState.FAILED
    assert result.result is None

    events = read_events(result.run_path)
    assert started_tool_names(events) == []
    assert completed_tool_names(events) == []
    assert media.candidate_calls == 0
    assert media.extracted_frame_calls == 0
    assert media.audio_calls == []

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "FAILED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_repeated_paid_sample_evidence_is_rejected_before_second_execution(
    tmp_path: Path,
) -> None:
    """Canonical-equivalent repeat of a completed paid call terminates the run FAILED.

    The second decision restates the first with int/float-canonical-equivalent
    arguments. Exactly one sample_evidence span may ever start or complete, the
    scripted final decision must never be consumed, and the run must terminate
    FAILED with no result and no verification.
    """
    decisions = [
        tool_decision(
            "sample_evidence",
            windows=[{"start_seconds": 0, "end_seconds": 2}],
            max_frames=1,
        ),
        tool_decision(
            "sample_evidence",
            windows=[{"start_seconds": 0.0, "end_seconds": 2.0}],
            max_frames=1,
        ),
        final_decision("frame-001"),
    ]
    result, model, media = await run_scripted_agent(decisions, tmp_path)

    assert model.plan_tools_calls == 0

    events = read_events(result.run_path)
    assert completed_tool_names(events) == ["sample_evidence"], (
        "a canonical-equivalent repeat of a paid sample_evidence call must be "
        "rejected before a second execution"
    )
    assert started_tool_names(events) == ["sample_evidence"]
    assert media.candidate_calls == 1, "the duplicate call must never reach the media port"
    assert media.extracted_frame_calls == 1

    assert len(model.requests) == 2, (
        "the duplicate rejection must terminate before any later decision"
    )
    assert len(model.decisions) == 1, "the scripted final decision must never be consumed"

    assert result.terminal_state is TerminalState.FAILED
    assert result.result is None
    assert result.verification is None

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "FAILED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_seventh_tool_call_is_exhausted_and_never_executes(tmp_path: Path) -> None:
    six_unique_calls = [
        tool_decision("transcribe_audio"),
        tool_decision("transcribe_audio", windows=[{"start_seconds": 0, "end_seconds": 2}]),
        tool_decision(
            "sample_evidence",
            windows=[{"start_seconds": 0, "end_seconds": 2}],
            max_frames=1,
        ),
        tool_decision(
            "sample_evidence",
            windows=[{"start_seconds": 2, "end_seconds": 4}],
            max_frames=1,
        ),
        tool_decision(
            "sample_evidence",
            windows=[{"start_seconds": 4, "end_seconds": 6}],
            max_frames=1,
        ),
        tool_decision(
            "sample_evidence",
            windows=[{"start_seconds": 6, "end_seconds": 8}],
            max_frames=1,
        ),
    ]
    seventh_call = tool_decision(
        "sample_evidence",
        windows=[{"start_seconds": 0, "end_seconds": 1}],
        max_frames=1,
    )
    result, model, media = await run_scripted_agent([*six_unique_calls, seventh_call], tmp_path)

    assert model.plan_tools_calls == 0

    events = read_events(result.run_path)
    assert len(completed_tool_names(events)) == 6
    assert len(started_tool_names(events)) == 6, (
        "the seventh tool call must never open an execution span"
    )
    # FakeFFmpeg only yields candidates inside three of the four sampled windows,
    # so exactly three sample calls reach extract_frames; the seventh adds none.
    assert media.extracted_frame_calls == 3

    assert result.terminal_state is TerminalState.EXHAUSTED
    assert result.result is None

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "EXHAUSTED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_invalid_arguments_are_rejected_before_plugin_execution(tmp_path: Path) -> None:
    decisions = [tool_decision("sample_evidence", max_frames=0)]
    result, model, media = await run_scripted_agent(decisions, tmp_path)

    assert model.plan_tools_calls == 0
    assert result.terminal_state is TerminalState.FAILED
    assert result.result is None

    events = read_events(result.run_path)
    assert started_tool_names(events) == [], (
        "invalid arguments must be rejected before any tool span starts"
    )
    assert completed_tool_names(events) == []
    assert media.candidate_calls == 0
    assert media.extracted_frame_calls == 0
    assert media.audio_calls == []

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "FAILED"
    assert manifest["finalized_at"] is not None


RAW_MALFORMED_BODY = '```json\n{"kind": "tool_calls", "calls": "not-a-list"}\n```'


class ErrorThenScriptedAgentModel(ScriptedAgentModel):
    """Scripted agent whose first N decide_next calls raise one configured error."""

    def __init__(
        self,
        decisions: Sequence[AgentDecision],
        *,
        error: ProviderError,
        error_count: int = 1,
    ) -> None:
        super().__init__(decisions)
        self.error = error
        self.error_remaining = error_count

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        if self.error_remaining > 0:
            self.requests.append(request)
            self.error_remaining -= 1
            raise self.error
        return await super().decide_next(request)


async def run_error_scripted_agent(
    model: ErrorThenScriptedAgentModel, tmp_path: Path
) -> HarnessRunResult:
    """Run one public agentic harness invocation against an error-scripted agent."""
    harness = VideoHarness(
        media=FakeFFmpeg(has_audio=True),
        model=model,
        recognizer=LegacyFakeRecognizer(text=TRANSCRIPT_TEXT),
        planner=model,
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    result = await harness.run(
        VideoSource(path=source_path),
        VideoGoal(objective="Answer only from captured local evidence"),
        HarnessPolicy(tool_mode="agentic", output_dir=tmp_path / "run"),
    )
    return result


def failed_agent_decision_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        event
        for event in events_of_type(events, "agent.decision")
        if event.get("status") == "failed"
    ]


@pytest.mark.asyncio
async def test_one_time_format_repair_recovers_a_malformed_first_decision(tmp_path: Path) -> None:
    """One malformed body earns exactly one format_repair retry, then the run succeeds."""
    assert AgentDecisionFormatError is not None, (
        "Task 8 must define AgentDecisionFormatError in vidsnap.providers.base"
    )
    model = ErrorThenScriptedAgentModel(
        [
            tool_decision("sample_evidence", max_frames=1),
            final_decision("frame-001"),
        ],
        error=AgentDecisionFormatError(f"malformed agent decision: {RAW_MALFORMED_BODY}"),
        error_count=1,
    )
    result = await run_error_scripted_agent(model, tmp_path)

    assert model.plan_tools_calls == 0
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.result is not None
    assert result.verification is not None
    assert result.verification.passed is True

    assert len(model.requests) == 3, (
        "one failed attempt plus the tool decision and the final decision"
    )
    assert model.requests[0].format_repair is False
    assert model.requests[1].format_repair is True, (
        "the single retry after a malformed decision must be marked format_repair"
    )
    assert model.requests[2].format_repair is False
    assert len(model.decisions) == 0, "both scripted decisions are consumed after recovery"

    events = read_events(result.run_path)
    assert completed_tool_names(events) == ["sample_evidence"]

    failed_requests = events_of_type(events, "model.request.failed")
    assert len(failed_requests) == 1, "the malformed attempt must fail its model.request span"
    started_correlations = {
        event["correlation_id"] for event in events_of_type(events, "model.request.started")
    }
    assert failed_requests[0]["correlation_id"] in started_correlations
    assert len(events_of_type(events, "model.request.completed")) == 2

    failed_decisions = failed_agent_decision_events(events)
    assert len(failed_decisions) == 1, (
        "the malformed attempt must leave one failed agent.decision event"
    )
    assert failed_decisions[0]["sequence"] > failed_requests[0]["sequence"]
    assert RAW_MALFORMED_BODY not in (result.run_path / "events.jsonl").read_text(), (
        "no event may retain the raw malformed decision body"
    )
    payload = failed_decisions[0]["payload"]
    assert isinstance(payload, dict)
    assert not {"body", "raw", "content", "text"} & payload.keys()

    completed_decisions = [
        event
        for event in events_of_type(events, "agent.decision")
        if event.get("status") == "completed"
    ]
    assert [event["payload"]["kind"] for event in completed_decisions] == ["tool_calls", "final"]

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "SUCCEEDED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_two_malformed_decisions_terminate_failed_after_two_model_calls(
    tmp_path: Path,
) -> None:
    """A second malformed decision exhausts the one-time repair and fails the run."""
    assert AgentDecisionFormatError is not None, (
        "Task 8 must define AgentDecisionFormatError in vidsnap.providers.base"
    )
    model = ErrorThenScriptedAgentModel(
        [],
        error=AgentDecisionFormatError(f"malformed agent decision: {RAW_MALFORMED_BODY}"),
        error_count=2,
    )
    result = await run_error_scripted_agent(model, tmp_path)

    assert model.plan_tools_calls == 0
    assert result.terminal_state is TerminalState.FAILED
    assert result.result is None
    assert result.verification is None

    assert len(model.requests) == 2, "exactly two model calls: original plus one repair retry"
    assert model.requests[0].format_repair is False
    assert model.requests[1].format_repair is True, (
        "only the second request may carry the format_repair flag"
    )
    assert len(model.decisions) == 0

    events = read_events(result.run_path)
    assert started_tool_names(events) == []
    assert completed_tool_names(events) == []
    assert len(events_of_type(events, "model.request.failed")) == 2
    assert len(events_of_type(events, "model.request.completed")) == 0
    assert len(failed_agent_decision_events(events)) == 2
    assert RAW_MALFORMED_BODY not in (result.run_path / "events.jsonl").read_text()

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "FAILED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_ordinary_provider_error_gets_no_format_repair_retry(tmp_path: Path) -> None:
    """Transport/provider failures stay ordinary ProviderError and fail immediately."""
    model = ErrorThenScriptedAgentModel(
        [final_decision("frame-001")],
        error=ProviderError("Qwen agent-decision request failed"),
        error_count=1,
    )
    result = await run_error_scripted_agent(model, tmp_path)

    assert model.plan_tools_calls == 0
    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason == "provider error"
    assert result.result is None

    assert len(model.requests) == 1, "ordinary ProviderError must never earn a retry"
    assert model.requests[0].format_repair is False
    assert len(model.decisions) == 1, "the scripted decision must never be consumed"

    events = read_events(result.run_path)
    assert len(events_of_type(events, "model.request.failed")) == 1
    assert started_tool_names(events) == []
    assert completed_tool_names(events) == []

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "FAILED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_agentic_run_without_planner_returns_blocked_without_raising(
    tmp_path: Path,
) -> None:
    """An agentic run without a decide_next planner must return BLOCKED, not raise.

    Today _run_agentic raises ProviderUnavailable before creating any RunBundle,
    so this test is RED: the expected GREEN behavior is a truthful BLOCKED result
    with no result, no tool events, exactly one finalized manifest, and any
    started model.request span closed by one paired failed/blocked event.
    """
    output_dir = tmp_path / "run"
    harness = VideoHarness(
        media=FakeFFmpeg(has_audio=True),
        model=FakeVideoModel(),
        recognizer=LegacyFakeRecognizer(text=TRANSCRIPT_TEXT),
        planner=None,
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    result = await harness.run(
        VideoSource(path=source_path),
        VideoGoal(objective="Answer only from captured local evidence"),
        HarnessPolicy(tool_mode="agentic", output_dir=output_dir),
    )

    assert result.terminal_state is TerminalState.BLOCKED
    assert result.failure_reason == "provider unavailable"
    assert result.result is None

    events = read_events(result.run_path)
    assert started_tool_names(events) == []
    assert completed_tool_names(events) == []
    assert events_of_type(events, "agent.decision") == []

    assert len(list(output_dir.rglob("manifest.json"))) == 1, (
        "exactly one finalized manifest may exist for the run"
    )
    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "BLOCKED"
    assert manifest["finalized_at"] is not None

    for started in events_of_type(events, "model.request.started"):
        correlation = started["correlation_id"]
        terminals = [
            event
            for event in events
            if event.get("event_type") in {"model.request.failed", "model.request.blocked"}
            and event.get("correlation_id") == correlation
        ]
        assert len(terminals) == 1, (
            "every started model.request span must close with exactly one terminal event"
        )
