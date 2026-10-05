"""Failed model requests and failed runs carry machine-readable failure records.

A failed ``model.request`` records ``payload.failure`` in the
``vidsnap.provider-failure/v1`` shape; the terminal run event records
``payload.failure`` in the ``vidsnap.run-failure/v1`` shape. Categories come
from a fixed allow-list; no exception text, URL, key, or provider body is kept.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest
from fakes import CancellingTranscriber, ScriptedAgentModel, tool_decision
from test_fixed_policy import build_context, make_kernel, read_events

from vidsnap.contracts import Evidence, ProviderFailure, TerminalState, VideoGoal
from vidsnap.contracts.agent import AgentDecision
from vidsnap.providers.base import (
    AgentDecisionFormatError,
    AgentDecisionResponse,
    AgentStepRequest,
    ModelResponse,
    ProviderError,
)
from vidsnap.runtime import AgenticPolicy, FixedPolicy, HarnessKernel, default_plugin_registry
from vidsnap.video.probe import FFmpegError, MediaProbe


class _FailingVideoModel:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    async def analyze_evidence(
        self, evidence: Sequence[Evidence], goal: VideoGoal
    ) -> ModelResponse:
        del evidence, goal
        raise self.error


class _FailingAgentModel:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        del request
        self.calls += 1
        raise self.error


class _FailingProbeMedia:
    """Delegates everything to a working fake except a probe that fails."""

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    async def probe(self, source: Path) -> MediaProbe:
        del source
        raise FFmpegError("ffprobe failed (1): sentinel-ffprobe-detail")


def _events(context: object, event_type: str) -> list[dict[str, object]]:
    run_path = context.bundle.path  # type: ignore[attr-defined]
    return [event for event in read_events(run_path) if event.get("event_type") == event_type]


def _terminal_run_event(context: object) -> dict[str, object]:
    run_path = context.bundle.path  # type: ignore[attr-defined]
    terminals = [
        event
        for event in read_events(run_path)
        if str(event.get("event_type", "")).startswith("run.") and event.get("status") != "started"
    ]
    assert len(terminals) == 1
    return terminals[0]


def _run_failure(context: object) -> object:
    payload = _terminal_run_event(context)["payload"]
    assert isinstance(payload, dict)
    return payload["failure"]


def _agentic_kernel() -> HarnessKernel:
    return HarnessKernel(policy=AgenticPolicy(), registry=default_plugin_registry())


@pytest.mark.asyncio
async def test_failed_model_request_records_provider_failure_and_partial_usage(
    tmp_path: Path,
) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    failure = ProviderFailure(category="http_5xx", http_status=503, input_bytes=1234)
    context.task_model = _FailingVideoModel(ProviderError("Qwen request failed", failure=failure))

    result = await make_kernel().run(context)

    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason == "provider error"
    (failed,) = _events(context, "model.request.failed")
    assert failed["payload"] == {
        "failure": {
            "schema_version": "vidsnap.provider-failure/v1",
            "category": "http_5xx",
            "http_status": 503,
            "input_bytes": 1234,
            "input_tokens": None,
            "output_tokens": None,
        }
    }
    # Measured request bytes are kept; unreported tokens stay flagged, never "zero cost".
    assert failed["usage"]["input_bytes"] == 1234
    assert failed["usage"]["model_calls"] == 1
    assert failed["usage"]["provider_reported"] is False
    terminal = _terminal_run_event(context)
    assert terminal["event_type"] == "run.failed"
    assert terminal["payload"]["failure"] == {
        "schema_version": "vidsnap.run-failure/v1",
        "category": "http_5xx",
        "http_status": 503,
        "reason": "provider error",
    }


@pytest.mark.asyncio
async def test_failure_with_provider_reported_usage_is_marked_reported(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    failure = ProviderFailure(
        category="invalid_response", input_bytes=99, input_tokens=40, output_tokens=6
    )
    context.task_model = _FailingVideoModel(ProviderError("bad body", failure=failure))

    await make_kernel().run(context)

    (failed,) = _events(context, "model.request.failed")
    assert failed["payload"]["failure"]["input_tokens"] == 40
    assert failed["payload"]["failure"]["output_tokens"] == 6
    assert failed["usage"]["input_tokens"] == 40
    assert failed["usage"]["output_tokens"] == 6
    assert failed["usage"]["provider_reported"] is True


@pytest.mark.asyncio
async def test_unclassified_model_exception_is_recorded_as_unknown(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.task_model = _FailingVideoModel(RuntimeError("sentinel-exception-text-77aa"))

    result = await make_kernel().run(context)

    assert result.failure_reason == "unexpected kernel error"
    (failed,) = _events(context, "model.request.failed")
    assert failed["payload"]["failure"]["category"] == "unknown"
    assert failed.get("usage") is None
    assert _run_failure(context) == {
        "schema_version": "vidsnap.run-failure/v1",
        "category": "unknown",
        "http_status": None,
        "reason": "unexpected kernel error",
    }
    ledger = (context.bundle.path / "events.jsonl").read_text(encoding="utf-8")
    assert "sentinel-exception-text-77aa" not in ledger


@pytest.mark.asyncio
async def test_provider_error_without_detail_is_provider_error(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.task_model = _FailingVideoModel(ProviderError("opaque"))

    await make_kernel().run(context)

    (failed,) = _events(context, "model.request.failed")
    assert failed["payload"]["failure"]["category"] == "provider_error"
    assert _run_failure(context)["category"] == "provider_error"  # type: ignore[index]


@pytest.mark.asyncio
async def test_missing_agent_model_blocks_with_provider_unavailable(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.agent_model = None

    result = await _agentic_kernel().run(context)

    assert result.terminal_state is TerminalState.BLOCKED
    (blocked,) = _events(context, "model.request.blocked")
    assert blocked["payload"]["failure"]["category"] == "provider_unavailable"
    terminal = _terminal_run_event(context)
    assert terminal["event_type"] == "run.blocked"
    assert terminal["payload"]["failure"]["category"] == "provider_unavailable"
    assert terminal["payload"]["failure"]["reason"] == "provider unavailable"


@pytest.mark.asyncio
async def test_repeated_format_errors_record_invalid_response(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    agent = _FailingAgentModel(AgentDecisionFormatError("fenced"))
    context.agent_model = agent

    result = await _agentic_kernel().run(context)

    assert result.terminal_state is TerminalState.FAILED
    assert agent.calls == 2  # one bounded format repair, unchanged
    failed = _events(context, "model.request.failed")
    assert [event["payload"]["failure"]["category"] for event in failed] == [
        "invalid_response",
        "invalid_response",
    ]
    assert _run_failure(context)["category"] == "invalid_response"  # type: ignore[index]


@pytest.mark.asyncio
async def test_cancelled_run_records_cancelled(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.recognizer = CancellingTranscriber()

    result = await make_kernel().run(context)

    assert result.failure_reason == "cancelled"
    assert _run_failure(context)["category"] == "cancelled"  # type: ignore[index]


@pytest.mark.asyncio
async def test_cancelled_model_request_records_cancelled(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.task_model = _FailingVideoModel(asyncio.CancelledError())

    await make_kernel().run(context)

    (failed,) = _events(context, "model.request.failed")
    assert failed["payload"]["failure"]["category"] == "cancelled"


@pytest.mark.asyncio
async def test_wall_clock_exhaustion_records_run_deadline(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    ticks = iter([0.0, 0.0])

    def clock() -> float:
        return next(ticks, 10_000.0)

    kernel = HarnessKernel(
        policy=FixedPolicy(),
        registry=default_plugin_registry(),
        clock=clock,
    )

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.EXHAUSTED
    assert result.failure_reason == "wall-clock budget exceeded"
    assert _terminal_run_event(context)["event_type"] == "run.failed"
    assert _run_failure(context)["category"] == "run_deadline"  # type: ignore[index]


@pytest.mark.asyncio
async def test_other_budget_exhaustion_records_budget_exhausted(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.policy = context.policy.model_copy(update={"max_tool_calls": 0})

    result = await make_kernel().run(context)

    assert result.terminal_state is TerminalState.EXHAUSTED
    assert result.failure_reason == "tool-call budget exceeded"
    assert _run_failure(context)["category"] == "budget_exhausted"  # type: ignore[index]


@pytest.mark.asyncio
async def test_invalid_model_requested_tool_arguments_record_validation(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.agent_model = ScriptedAgentModel([tool_decision("sample_evidence", max_frames=0)])

    result = await _agentic_kernel().run(context)

    assert result.terminal_state is TerminalState.FAILED
    assert _run_failure(context)["category"] == "validation"  # type: ignore[index]


@pytest.mark.asyncio
async def test_unknown_model_requested_tool_records_validation(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.agent_model = ScriptedAgentModel(
        [AgentDecision(kind="tool_calls", calls=({"name": "open_url", "arguments": {}},))]
    )

    await _agentic_kernel().run(context)

    assert _run_failure(context)["category"] == "validation"  # type: ignore[index]


@pytest.mark.asyncio
async def test_out_of_range_tool_window_records_validation(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.agent_model = ScriptedAgentModel(
        [
            tool_decision(
                "sample_evidence",
                windows=[{"start_seconds": 50.0, "end_seconds": 60.0}],
            )
        ]
    )

    await _agentic_kernel().run(context)

    assert _run_failure(context)["category"] == "validation"  # type: ignore[index]


@pytest.mark.asyncio
async def test_media_probe_failure_records_media_error(tmp_path: Path) -> None:
    context, media, *_ = build_context(tmp_path, has_audio=True)
    context.media = _FailingProbeMedia(media)  # type: ignore[assignment]

    result = await make_kernel().run(context)

    assert result.terminal_state is TerminalState.FAILED
    assert _run_failure(context)["category"] == "media_error"  # type: ignore[index]
    ledger = (context.bundle.path / "events.jsonl").read_text(encoding="utf-8")
    assert "sentinel-ffprobe-detail" not in ledger


@pytest.mark.asyncio
async def test_successful_run_records_a_null_failure(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)

    result = await make_kernel().run(context)

    assert result.terminal_state is TerminalState.SUCCEEDED
    terminal = _terminal_run_event(context)
    assert terminal["event_type"] == "run.completed"
    assert terminal["payload"]["terminal_state"] == "SUCCEEDED"
    assert terminal["payload"]["failure"] is None
    assert _events(context, "model.request.failed") == []
