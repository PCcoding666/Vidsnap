"""Regression test: artifact allocation failure must never orphan a tool.call span.

If artifact directory allocation (context.next_artifact_dir) or the
ToolExecutionContext setup raises after tool.call.started, the same span must
always be finished with failed status and the RunBundle must still reach a
truthful finalized FAILED terminal state.
"""

from __future__ import annotations

import json

import pytest
from test_fixed_policy import build_context, make_kernel, read_events

from vidsnap.contracts import TerminalState

TERMINAL_STATUSES = {"completed", "failed", "blocked", "skipped"}


def terminal_events_for(
    events: list[dict[str, object]], correlation_id: object
) -> list[dict[str, object]]:
    return [
        event
        for event in events
        if event.get("correlation_id") == correlation_id
        and event.get("status") in TERMINAL_STATUSES
    ]


@pytest.mark.asyncio
async def test_artifact_allocation_failure_pairs_tool_span_and_finalizes_failed(tmp_path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    # Block the first artifact allocation so next_artifact_dir() raises FileExistsError.
    (context.bundle.path / "artifacts" / "call-001").write_bytes(b"blocked")
    kernel = make_kernel()

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason is not None

    events = read_events(context.bundle.path)
    tool_started = [event for event in events if event.get("event_type") == "tool.call.started"]
    assert tool_started, "expected a tool.call.started span before allocation failed"
    for span in tool_started:
        correlation_id = span.get("correlation_id")
        assert correlation_id, f"tool.call.started missing correlation_id: {span}"
        terminals = terminal_events_for(events, correlation_id)
        assert len(terminals) == 1, (
            f"tool.call span {correlation_id} has {len(terminals)} terminal events "
            "after allocation failure, expected exactly one"
        )
        assert terminals[0].get("status") == "failed", (
            f"tool.call span {correlation_id} must finish failed, got {terminals[0]}"
        )
        assert terminals[0].get("event_type") == "tool.call.failed"

    for span in (event for event in events if event.get("status") == "started"):
        correlation_id = span.get("correlation_id")
        assert correlation_id, f"started span missing correlation_id: {span}"
        assert len(terminal_events_for(events, correlation_id)) == 1, (
            f"started span {span.get('event_type')} correlation {correlation_id} "
            "is unpaired after allocation failure"
        )

    manifest = json.loads((context.bundle.path / "manifest.json").read_text())
    assert manifest["terminal_state"] == "FAILED"
    assert manifest["finalized_at"] is not None
