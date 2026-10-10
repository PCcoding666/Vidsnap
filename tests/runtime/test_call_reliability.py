"""Real kernel/provider failure paths with offline media and HTTP transport."""

import asyncio
import json
from contextlib import suppress

import httpx
import pytest
from test_fixed_policy import (
    assert_started_spans_are_balanced,
    build_context,
    make_kernel,
    read_events,
)

from vidsnap.contracts import HarnessPolicy, TerminalState
from vidsnap.providers.qwen import QwenCompatibleClient
from vidsnap.runtime import AgenticPolicy, HarnessKernel, default_plugin_registry
from vidsnap.trace.reader import read_trace


@pytest.mark.asyncio
async def test_failed_model_call_retains_evidence_and_safe_trace_diagnostics(tmp_path):
    bodies = []

    async def handler(request):
        bodies.append(request.content)
        raise httpx.ReadTimeout("PRIVATE_RESPONSE_WITH_CREDENTIAL", request=request)

    context, *_ = build_context(tmp_path, has_audio=True)
    context.task_model = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler)
    )
    result = await make_kernel().run(context)
    assert result.terminal_state is TerminalState.FAILED
    assert len(bodies) == 1
    assert {item.modality for item in context.evidence} == {"frame", "transcript"}
    for item in context.evidence:
        assert (context.bundle.path / "evidence" / f"{item.id}.json").is_file()
        if item.artifact_path:
            assert item.artifact_path.is_file()
    events = read_events(context.bundle.path)
    assert_started_spans_are_balanced(events)
    failed = next(e for e in events if e["event_type"] == "model.request.failed")
    assert failed["payload"].get("failure", {}).get("category") == "read_timeout"
    assert failed["duration_ms"] is not None
    assert failed["usage"]["input_bytes"] == len(bodies[0])
    assert failed["usage"]["provider_reported"] is False
    trace = read_trace(context.bundle.path)
    assert "read_timeout" in trace.model_dump_json()
    assert "PRIVATE_RESPONSE_WITH_CREDENTIAL" not in trace.model_dump_json()
    assert (
        "PRIVATE_RESPONSE_WITH_CREDENTIAL" not in (context.bundle.path / "events.jsonl").read_text()
    )


@pytest.mark.asyncio
async def test_run_deadline_interrupts_model_and_finalizes_without_losing_evidence(tmp_path):
    stopped = asyncio.Event()
    bodies = []

    async def handler(request):
        bodies.append(request.content)
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    context, *_ = build_context(tmp_path, has_audio=True)
    context.policy = HarnessPolicy(max_wall_seconds=1)
    context.task_model = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler), timeout_seconds=10
    )
    # Outer guard keeps the RED test finite; it is not the expected run deadline.
    result = await asyncio.wait_for(make_kernel().run(context), timeout=2)
    assert result.terminal_state is TerminalState.EXHAUSTED
    assert result.failure_reason == "wall-clock budget exceeded"
    assert stopped.is_set()
    events = read_events(context.bundle.path)
    assert_started_spans_are_balanced(events)
    failed = next(e for e in events if e["event_type"] == "model.request.failed")
    assert failed["payload"]["failure"]["category"] == "run_deadline"
    assert failed["usage"]["input_bytes"] == len(bodies[0])
    assert failed["usage"]["provider_reported"] is False
    assert {item.modality for item in context.evidence} == {"frame", "transcript"}
    manifest = json.loads((context.bundle.path / "manifest.json").read_text())
    assert manifest["terminal_state"] == "EXHAUSTED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_explicit_cancellation_is_not_mislabelled_as_run_deadline(tmp_path):
    entered = asyncio.Event()

    async def handler(request):
        entered.set()
        await asyncio.Event().wait()

    context, *_ = build_context(tmp_path, has_audio=True)
    context.task_model = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler)
    )
    running = asyncio.create_task(make_kernel().run(context))
    await asyncio.wait_for(entered.wait(), timeout=1)
    running.cancel()
    result = await running
    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason == "cancelled"
    events = read_events(context.bundle.path)
    assert_started_spans_are_balanced(events)
    failed = next(e for e in events if e["event_type"] == "model.request.failed")
    assert failed["payload"].get("failure", {}).get("category") == "cancelled"


@pytest.mark.asyncio
async def test_malformed_model_result_keeps_provider_usage_in_failed_trace(tmp_path):
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "PRIVATE_MALFORMED_OUTPUT"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    context, *_ = build_context(tmp_path, has_audio=True)
    context.task_model = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler)
    )
    result = await make_kernel().run(context)
    assert result.terminal_state is TerminalState.FAILED
    events = read_events(context.bundle.path)
    assert_started_spans_are_balanced(events)
    failed = next(e for e in events if e["event_type"] == "model.request.failed")
    assert failed["payload"]["failure"]["category"] == "invalid_response"
    assert failed["usage"]["input_tokens"] == 7
    assert failed["usage"]["output_tokens"] == 3
    assert failed["usage"]["provider_reported"] is True
    assert "PRIVATE_MALFORMED_OUTPUT" not in json.dumps(events)


@pytest.mark.asyncio
async def test_run_deadline_cancels_stalled_probe_before_model_or_tools(tmp_path, monkeypatch):
    stopped = asyncio.Event()

    async def stalled_probe(path):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    context, media, model, agent, recognizer = build_context(tmp_path, has_audio=True)
    context.policy = HarnessPolicy(max_wall_seconds=1)
    monkeypatch.setattr(media, "probe", stalled_probe)
    result = await asyncio.wait_for(make_kernel().run(context), timeout=2)
    assert result.terminal_state is TerminalState.EXHAUSTED
    assert stopped.is_set()
    assert model.analyze_calls == agent.decide_next_calls == 0
    assert recognizer.calls == []
    events = read_events(context.bundle.path)
    assert_started_spans_are_balanced(events)
    probe = next(e for e in events if e["event_type"] == "probe.failed")
    assert probe["payload"]["failure"]["category"] == "run_deadline"


@pytest.mark.asyncio
async def test_agentic_failure_after_tool_batch_preserves_real_call_sequence(tmp_path):
    bodies = []

    async def handler(request):
        bodies.append(request.content)
        if len(bodies) == 1:
            decision = {
                "kind": "tool_calls",
                "calls": [
                    {"name": "transcribe_audio", "arguments": {}},
                    {"name": "sample_evidence", "arguments": {"max_frames": 2}},
                ],
            }
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps(decision)}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )
        raise httpx.ReadTimeout("PRIVATE_PROVIDER_RESPONSE", request=request)

    context, *_ = build_context(tmp_path, has_audio=True)
    context.agent_model = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler)
    )
    kernel = HarnessKernel(policy=AgenticPolicy(), registry=default_plugin_registry())
    result = await kernel.run(context)
    assert result.terminal_state is TerminalState.FAILED
    assert len(bodies) == context.model_calls == 2
    assert {item.modality for item in context.evidence} == {"frame", "transcript"}
    events = read_events(context.bundle.path)
    assert_started_spans_are_balanced(events)
    assert [
        e["event_type"]
        for e in events
        if e["event_type"]
        in {"model.request.completed", "tool.call.completed", "model.request.failed"}
    ] == [
        "model.request.completed",
        "tool.call.completed",
        "tool.call.completed",
        "model.request.failed",
    ]
    failed = next(e for e in events if e["event_type"] == "model.request.failed")
    assert failed["payload"]["failure"]["category"] == "read_timeout"
    assert failed["usage"]["input_bytes"] == len(bodies[1])
    assert failed["usage"]["provider_reported"] is False
    assert "PRIVATE_PROVIDER_RESPONSE" not in json.dumps(events)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_again", [False, True])
async def test_cancellation_cleanup_outlives_wall_timer_without_orphaning_request(
    tmp_path, cancel_again
):
    entered = asyncio.Event()
    cleaning = asyncio.Event()
    cleaned = asyncio.Event()
    release_cleanup = asyncio.Event()
    request_task = None

    async def handler(request):
        nonlocal request_task
        request_task = asyncio.current_task()
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release_cleanup.wait()
            cleaned.set()

    context, *_ = build_context(tmp_path, has_audio=True)
    context.policy = HarnessPolicy(max_wall_seconds=1)
    context.task_model = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler), timeout_seconds=10
    )
    running = asyncio.create_task(make_kernel().run(context))
    await entered.wait()
    running.cancel()
    await cleaning.wait()
    if cancel_again:
        running.cancel()
    try:
        await asyncio.sleep(1.1)
        assert not running.done(), "kernel must join cleanup even after its wall deadline"
        release_cleanup.set()
        result = await running
        assert result.terminal_state is TerminalState.FAILED
        assert result.failure_reason == "cancelled"
        assert cleaned.is_set() and request_task.done()
    finally:
        release_cleanup.set()
        if request_task is not None and not request_task.done():
            with suppress(asyncio.CancelledError):
                await request_task
        if not running.done():
            await running


@pytest.mark.asyncio
async def test_kernel_cancellation_at_response_completion_cannot_report_success(tmp_path):
    async def handler(request):
        asyncio.get_running_loop().call_soon(running.cancel)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary":"ok","claims":[]}'}}]},
        )

    context, *_ = build_context(tmp_path, has_audio=True)
    context.task_model = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler)
    )
    running = asyncio.create_task(make_kernel().run(context))
    result = await running
    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason == "cancelled"
    assert_started_spans_are_balanced(read_events(context.bundle.path))
