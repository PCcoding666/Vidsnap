"""Structured, allow-listed failure records attached by the built-in providers.

Every test uses ``httpx.MockTransport``: no network, no credential, no model.
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from vidsnap.contracts import Evidence, ProviderFailure, VideoGoal
from vidsnap.providers.asr import QwenAsrRecognizer
from vidsnap.providers.base import (
    AgentDecisionFormatError,
    AgentStepRequest,
    ProviderError,
    ProviderUnavailable,
)
from vidsnap.providers.qwen import QwenCompatibleClient
from vidsnap.video.probe import MediaProbe

_GOAL = VideoGoal(objective="Summarize the demonstration")
_PROBE = MediaProbe(duration_seconds=4.0, fps=24.0, width=320, height=240, has_audio=True)
_EVIDENCE = [
    Evidence(
        id="transcript-001", start_seconds=0, end_seconds=4, modality="transcript", content="hi"
    )
]


def _agent_request() -> AgentStepRequest:
    return AgentStepRequest(
        goal=_GOAL,
        probe=_PROBE,
        evidence=(),
        tool_results=(),
        tool_schemas=(),
        output_schema={"type": "object"},
        remaining_model_calls=1,
        remaining_tool_calls=1,
        remaining_frames=1,
    )


def _measured_bytes(request: httpx.Request) -> int:
    """The documented request-size measure: compact ASCII JSON of the request body."""
    body = json.loads(request.content)
    return len(json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))


def _client(handler: object) -> QwenCompatibleClient:
    return QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_provider_error_construction_stays_backward_compatible() -> None:
    assert ProviderError().failure is None
    assert ProviderError("plain message").failure is None
    assert str(ProviderError("plain message")) == "plain message"
    failure = ProviderFailure(category="http_5xx", http_status=503)
    assert ProviderUnavailable("blocked", failure=failure).failure == failure


def test_failure_payload_is_versioned_and_keeps_missing_measurements_null() -> None:
    failure = ProviderFailure(category="read_timeout", input_bytes=42)

    assert failure.as_payload() == {
        "schema_version": "vidsnap.provider-failure/v1",
        "category": "read_timeout",
        "http_status": None,
        "input_bytes": 42,
        "input_tokens": None,
        "output_tokens": None,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": "not_a_category"},
        {"category": "http_5xx", "http_status": 99},
        {"category": "http_5xx", "http_status": 600},
        {"category": "unknown", "input_bytes": -1},
        {"category": "unknown", "input_tokens": True},
        {"category": "unknown", "detail": "free text is not allowed"},
    ],
)
def test_failure_record_rejects_values_outside_the_allow_list(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProviderFailure.model_validate(kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "category"),
    [(503, "http_5xx"), (500, "http_5xx"), (401, "http_4xx"), (429, "http_4xx")],
)
async def test_analyze_http_status_failures_record_class_status_and_request_bytes(
    status: int, category: str
) -> None:
    seen: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(_measured_bytes(request))
        return httpx.Response(status, json={"error": {"message": "rejected"}})

    with pytest.raises(ProviderError) as excinfo:
        await _client(handler).analyze_evidence(_EVIDENCE, _GOAL)

    assert excinfo.value.failure == ProviderFailure(
        category=category, http_status=status, input_bytes=seen[0]
    )


@pytest.mark.asyncio
async def test_http_failure_keeps_only_validated_usage_counters_from_the_error_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            400,
            json={
                "error": {"code": "data_inspection_failed"},
                "usage": {"prompt_tokens": 120, "completion_tokens": 0, "secret": "x"},
            },
        )

    with pytest.raises(ProviderError) as excinfo:
        await _client(handler).analyze_evidence(_EVIDENCE, _GOAL)

    failure = excinfo.value.failure
    assert failure is not None
    assert (failure.category, failure.http_status) == ("http_4xx", 400)
    assert (failure.input_tokens, failure.output_tokens) == (120, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "category"),
    [
        (httpx.ConnectTimeout("connect"), "connect_timeout"),
        (httpx.ReadTimeout("read"), "read_timeout"),
        (httpx.WriteTimeout("write"), "write_timeout"),
        (httpx.PoolTimeout("pool"), "pool_timeout"),
        (httpx.ConnectError("refused"), "connection_error"),
        (httpx.RemoteProtocolError("reset"), "transport_error"),
    ],
)
async def test_transport_failures_are_categorized_without_an_http_status(
    exception: httpx.HTTPError, category: str
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise exception

    with pytest.raises(ProviderError) as excinfo:
        await _client(handler).analyze_evidence(_EVIDENCE, _GOAL)

    failure = excinfo.value.failure
    assert failure is not None
    assert failure.category == category
    assert failure.http_status is None
    assert failure.input_bytes is not None and failure.input_bytes > 0
    assert (failure.input_tokens, failure.output_tokens) == (None, None)


@pytest.mark.asyncio
async def test_analyze_invalid_json_body_is_a_provider_error_with_invalid_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=b"<html>gateway</html>")

    with pytest.raises(ProviderError) as excinfo:
        await _client(handler).analyze_evidence(_EVIDENCE, _GOAL)

    failure = excinfo.value.failure
    assert failure is not None and failure.category == "invalid_response"


@pytest.mark.asyncio
async def test_analyze_schema_invalid_result_keeps_reported_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"not": "a result"}'}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 9},
            },
        )

    with pytest.raises(ProviderError) as excinfo:
        await _client(handler).analyze_evidence(_EVIDENCE, _GOAL)

    failure = excinfo.value.failure
    assert failure is not None
    assert failure.category == "invalid_response"
    assert (failure.input_tokens, failure.output_tokens) == (50, 9)
    assert failure.input_bytes is not None and failure.input_bytes > 0


@pytest.mark.asyncio
async def test_plan_tools_http_failure_is_categorized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(502, json={})

    with pytest.raises(ProviderError) as excinfo:
        await _client(handler).plan_tools(_PROBE, _GOAL)

    failure = excinfo.value.failure
    assert failure is not None and (failure.category, failure.http_status) == ("http_5xx", 502)


@pytest.mark.asyncio
async def test_decide_next_http_failure_stays_plain_provider_error_with_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={})

    with pytest.raises(ProviderError) as excinfo:
        await _client(handler).decide_next(_agent_request())

    assert not isinstance(excinfo.value, AgentDecisionFormatError)
    failure = excinfo.value.failure
    assert failure is not None and (failure.category, failure.http_status) == ("http_5xx", 503)


@pytest.mark.asyncio
async def test_decide_next_format_failures_are_invalid_response_with_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "```json\n{}\n```"}}],
                "usage": {"prompt_tokens": 31, "completion_tokens": 4},
            },
        )

    with pytest.raises(AgentDecisionFormatError) as excinfo:
        await _client(handler).decide_next(_agent_request())

    failure = excinfo.value.failure
    assert failure is not None
    assert failure.category == "invalid_response"
    assert (failure.input_tokens, failure.output_tokens) == (31, 4)


@pytest.mark.asyncio
async def test_decide_next_non_json_body_is_invalid_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=b"not json")

    with pytest.raises(AgentDecisionFormatError) as excinfo:
        await _client(handler).decide_next(_agent_request())

    failure = excinfo.value.failure
    assert failure is not None and failure.category == "invalid_response"


@pytest.mark.asyncio
async def test_asr_http_failure_is_categorized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500, json={})

    recognizer = QwenAsrRecognizer(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as excinfo:
        await recognizer.transcribe(b"RIFF-audio")

    failure = excinfo.value.failure
    assert failure is not None and (failure.category, failure.http_status) == ("http_5xx", 500)


@pytest.mark.asyncio
async def test_failure_records_never_carry_urls_keys_or_bodies() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, json={"error": "sentinel-body-text-0f3e"})

    client = QwenCompatibleClient(api_key="sentinel-9a1b", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as excinfo:
        await client.analyze_evidence(_EVIDENCE, _GOAL)

    assert excinfo.value.failure is not None
    serialized = json.dumps(excinfo.value.failure.as_payload())
    for marker in ("sentinel-body-text-0f3e", "sentinel-9a1b", "https://", "Bearer"):
        assert marker not in serialized
