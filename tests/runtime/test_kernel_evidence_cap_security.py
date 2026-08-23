"""Security regression: an overproducing media port must not breach the frame cap.

A hostile or buggy FFmpegPort can return more extracted frames than the
candidates the sampler requested. The kernel must not trust plugin output:
after tool execution it must verify the actually retained frame count against
the policy cap, fail the tool span, emit a numeric budget snapshot, and
terminate EXHAUSTED before the task model ever sees the smuggled evidence.

Written RED-first against the current kernel, which trusts plugin output.
"""

from __future__ import annotations

import json

import pytest
from fakes import OverproducingFFmpeg
from test_fixed_policy import build_context, make_kernel, read_events

from vidsnap.contracts import HarnessPolicy, TerminalState

TERMINAL_STATUSES = {"completed", "failed", "blocked", "skipped"}


@pytest.mark.asyncio
async def test_overproducing_media_port_is_caught_before_synthesis(tmp_path) -> None:
    context, _media, video_model, _agent_model, _recognizer = build_context(
        tmp_path, has_audio=True
    )
    context.media = OverproducingFFmpeg(extra_frames=2)
    context.policy = HarnessPolicy(max_evidence_frames=1)
    kernel = make_kernel()

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.EXHAUSTED
    assert video_model.analyze_calls == 0, (
        "task model must never see evidence retained beyond the policy cap"
    )

    events = read_events(context.bundle.path)
    sample_started = [
        event
        for event in events
        if event.get("event_type") == "tool.call.started"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("name") == "sample_evidence"
    ]
    assert sample_started, "expected a started sample_evidence tool.call span"
    for span in sample_started:
        correlation_id = span.get("correlation_id")
        terminals = [
            event
            for event in events
            if event.get("correlation_id") == correlation_id
            and event.get("status") in TERMINAL_STATUSES
        ]
        assert len(terminals) == 1, (
            f"sample_evidence span {correlation_id} must have exactly one "
            f"terminal partner, got {len(terminals)}"
        )
        assert terminals[0].get("status") == "failed", (
            "the overproducing sample_evidence tool.call must be paired as failed"
        )

    budget_events = [event for event in events if event.get("event_type") == "budget.updated"]
    assert budget_events, "expected a numeric budget snapshot after the violation"
    for event in budget_events:
        payload = event.get("payload")
        assert isinstance(payload, dict) and payload
        for key, value in payload.items():
            assert isinstance(value, int) and not isinstance(value, bool)
            assert value >= 0, f"budget field {key!r} must be non-negative"

    manifest = json.loads((context.bundle.path / "manifest.json").read_text())
    assert manifest["terminal_state"] == "EXHAUSTED"
    assert manifest["finalized_at"] is not None
