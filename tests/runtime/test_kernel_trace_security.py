"""RED acceptance tests for the approved kernel event protocol and trace security.

These tests run the existing HarnessKernel + FixedPolicy against deterministic
fakes and assert the approved protocol without modifying any production code:

- exact event types: run.started/completed, probe.started/completed,
  tool.call.started/completed, model.request.started/completed,
  verifier.completed, budget.updated;
- every started run/probe/model.request/tool.call span has exactly one
  same-correlation completed/failed/blocked/skipped event;
- tool.call completed payloads expose `name` in real execution order;
- silent media emits no transcribe_audio tool.call and does not spend a
  tool_calls unit on it;
- budget.updated events expose only non-negative numeric counters and appear
  whenever model/tool/frame/iteration budgets change;
- the finalized manifest records terminal_state SUCCEEDED;
- cancellation is truthfully recorded as FAILED with reason "cancelled", with
  every span paired and the manifest finalized.

They are written RED-first and are expected to fail against current production.
"""

from __future__ import annotations

import json

import pytest
from fakes import CancellingTranscriber
from test_fixed_policy import build_context, make_kernel, read_events

from vidsnap.contracts import TerminalState

APPROVED_STARTED_TYPES = (
    "run.started",
    "probe.started",
    "model.request.started",
    "tool.call.started",
)
APPROVED_EVENT_TYPES = APPROVED_STARTED_TYPES + (
    "run.completed",
    "probe.completed",
    "tool.call.completed",
    "model.request.completed",
    "verifier.completed",
    "budget.updated",
)
TERMINAL_STATUSES = {"completed", "failed", "blocked", "skipped"}
APPROVED_TOOL_NAMES = {"transcribe_audio", "sample_evidence"}


def events_of_type(events: list[dict[str, object]], event_type: str) -> list[dict[str, object]]:
    return [event for event in events if event.get("event_type") == event_type]


def terminal_events_for(
    events: list[dict[str, object]], correlation_id: object
) -> list[dict[str, object]]:
    return [
        event
        for event in events
        if event.get("correlation_id") == correlation_id
        and event.get("status") in TERMINAL_STATUSES
    ]


def tool_call_names(events: list[dict[str, object]], event_type: str) -> list[object]:
    """Ordered `name` values from tool.call events, as they really executed."""
    names: list[object] = []
    for event in events_of_type(events, event_type):
        payload = event.get("payload")
        assert isinstance(payload, dict), f"tool.call event missing payload: {event}"
        names.append(payload.get("name"))
    return names


@pytest.mark.asyncio
async def test_approved_event_types_are_emitted(tmp_path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    await kernel.run(context)

    events = read_events(context.bundle.path)
    observed = {event.get("event_type") for event in events}
    missing = set(APPROVED_EVENT_TYPES) - observed
    assert not missing, f"approved event types missing from ledger: {sorted(missing)}"


@pytest.mark.asyncio
async def test_every_approved_started_span_has_one_terminal_partner(tmp_path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    await kernel.run(context)

    events = read_events(context.bundle.path)
    for started_type in APPROVED_STARTED_TYPES:
        started = events_of_type(events, started_type)
        assert started, f"expected at least one {started_type} event"
        for span in started:
            correlation_id = span.get("correlation_id")
            assert correlation_id, f"{started_type} event missing correlation_id: {span}"
            terminals = terminal_events_for(events, correlation_id)
            assert len(terminals) == 1, (
                f"{started_type} correlation {correlation_id} has "
                f"{len(terminals)} terminal events, expected exactly one"
            )


@pytest.mark.asyncio
async def test_tool_call_completed_payloads_expose_names_in_real_order(tmp_path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    await kernel.run(context)

    events = read_events(context.bundle.path)
    names = tool_call_names(events, "tool.call.completed")
    assert names, "expected tool.call.completed events for a run that executes tools"
    for name in names:
        assert name in APPROVED_TOOL_NAMES, f"unexpected tool.call name: {name!r}"
    assert names == ["transcribe_audio", "sample_evidence"]


@pytest.mark.asyncio
async def test_silent_media_emits_no_transcribe_tool_call(tmp_path) -> None:
    context, _media, _video_model, _agent_model, recognizer = build_context(
        tmp_path, has_audio=False
    )
    kernel = make_kernel()

    await kernel.run(context)

    assert recognizer.calls == []
    events = read_events(context.bundle.path)
    started_names = tool_call_names(events, "tool.call.started")
    completed_names = tool_call_names(events, "tool.call.completed")
    assert "transcribe_audio" not in started_names
    assert "transcribe_audio" not in completed_names
    assert completed_names == ["sample_evidence"]
    assert context.tool_calls == 1, (
        "silent media must not spend a tool_calls unit on transcribe_audio"
    )


@pytest.mark.asyncio
async def test_budget_updated_events_are_numeric_and_track_changes(tmp_path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    await kernel.run(context)

    events = read_events(context.bundle.path)
    budget_events = events_of_type(events, "budget.updated")
    assert budget_events, "expected budget.updated events when budgets change"
    for event in budget_events:
        payload = event.get("payload")
        assert isinstance(payload, dict) and payload, (
            f"budget.updated must expose a non-empty payload: {event}"
        )
        for key, value in payload.items():
            assert isinstance(value, int) and not isinstance(value, bool), (
                f"budget.updated field {key!r} must be numeric, got {value!r}"
            )
            assert value >= 0, f"budget.updated field {key!r} must be non-negative"
    observed_budget_changes = context.iterations + context.tool_calls + context.model_calls
    assert len(budget_events) >= observed_budget_changes, (
        f"expected at least {observed_budget_changes} budget.updated events, "
        f"got {len(budget_events)}"
    )


@pytest.mark.asyncio
async def test_finalized_manifest_records_succeeded(tmp_path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.SUCCEEDED
    manifest = json.loads((context.bundle.path / "manifest.json").read_text())
    assert manifest["terminal_state"] == "SUCCEEDED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_cancellation_is_truthfully_recorded_and_finalized(tmp_path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.recognizer = CancellingTranscriber()
    kernel = make_kernel()

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason == "cancelled"

    events = read_events(context.bundle.path)
    started = [event for event in events if event.get("status") == "started"]
    assert started, "expected at least one started span in a cancelled run"
    for span in started:
        correlation_id = span.get("correlation_id")
        assert correlation_id, f"started span missing correlation_id: {span}"
        terminals = terminal_events_for(events, correlation_id)
        assert len(terminals) == 1, (
            f"started event {span.get('event_type')} correlation {correlation_id} "
            f"has {len(terminals)} terminal events after cancellation, expected one"
        )

    manifest = json.loads((context.bundle.path / "manifest.json").read_text())
    assert manifest["terminal_state"] == "FAILED"
    assert manifest["finalized_at"] is not None
