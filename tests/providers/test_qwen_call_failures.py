"""Offline acceptance for safe failures, actual bytes and bounded Qwen calls."""

import asyncio
import json

import httpx
import pytest
from test_qwen import make_agent_request

from vidsnap.contracts import VideoGoal
from vidsnap.providers.base import AgentDecisionFormatError, ProviderError, ProviderFailure
from vidsnap.providers.qwen import QwenCompatibleClient


async def invoke(client, operation):
    request = make_agent_request()
    if operation == "agent":
        return await client.decide_next(request)
    if operation == "plan":
        return await client.plan_tools(request.probe, request.goal)
    return await client.analyze_evidence([], VideoGoal(objective="Summarize the clip"))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["agent", "plan", "analyze"])
@pytest.mark.parametrize(
    ("error_type", "category"),
    [
        (httpx.ConnectTimeout, "connect_timeout"),
        (httpx.ReadTimeout, "read_timeout"),
        (httpx.WriteTimeout, "write_timeout"),
        (httpx.PoolTimeout, "pool_timeout"),
        (httpx.ConnectError, "connection_error"),
        (httpx.RemoteProtocolError, "transport_error"),
    ],
)
async def test_transport_failures_keep_safe_category_and_measured_bytes(
    operation, error_type, category
):
    bodies = []

    async def handler(request):
        bodies.append(request.content)
        raise error_type("PRIVATE_PROVIDER_PAYLOAD", request=request)

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await invoke(client, operation)
    failure = getattr(caught.value, "failure", None)
    assert failure is not None, "failed calls must retain structured diagnostics"
    assert failure.category == category
    assert failure.input_bytes == len(bodies[0])
    assert failure.input_tokens is None and failure.output_tokens is None
    assert failure.http_status is None
    assert len(bodies) == 1, "transport failures must not silently retry"
    assert not isinstance(caught.value, AgentDecisionFormatError)
    assert "PRIVATE_PROVIDER_PAYLOAD" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["agent", "plan", "analyze"])
async def test_http_status_is_retained_without_response_body_or_headers(operation):
    async def handler(request):
        return httpx.Response(
            429,
            text="PRIVATE_PROVIDER_PAYLOAD",
            headers={"x-private-value": "PRIVATE_HEADER"},
        )

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await invoke(client, operation)
    failure = getattr(caught.value, "failure", None)
    assert failure is not None
    assert failure.category == "http_error"
    assert failure.http_status == 429
    assert failure.input_bytes > 0
    assert "PRIVATE" not in json.dumps(failure.as_payload())
    assert not isinstance(caught.value, AgentDecisionFormatError)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["agent", "plan", "analyze"])
async def test_invalid_model_output_preserves_reported_usage(operation):
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "PRIVATE_INVALID_OUTPUT"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await invoke(client, operation)
    failure = getattr(caught.value, "failure", None)
    assert failure is not None
    assert failure.category == "invalid_response"
    assert (failure.input_tokens, failure.output_tokens) == (7, 3)
    assert failure.input_bytes > 0
    assert isinstance(caught.value, AgentDecisionFormatError) == (operation == "agent")
    assert "PRIVATE_INVALID_OUTPUT" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["agent", "plan", "analyze"])
async def test_non_json_http_body_is_a_safe_provider_failure(operation):
    async def handler(request):
        return httpx.Response(200, text="PRIVATE_NON_JSON_RESPONSE")

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await invoke(client, operation)
    failure = getattr(caught.value, "failure", None)
    assert failure is not None
    assert failure.category == "invalid_response"
    assert failure.input_bytes > 0
    assert failure.input_tokens is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["agent", "plan", "analyze"])
async def test_request_deadline_interrupts_a_stalled_transport(operation):
    stopped = asyncio.Event()

    async def handler(request):
        try:
            await asyncio.sleep(0.15)
            return httpx.Response(503)
        finally:
            stopped.set()

    client = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler), timeout_seconds=0.02
    )
    with pytest.raises(ProviderError) as caught:
        await invoke(client, operation)
    failure = getattr(caught.value, "failure", None)
    assert failure is not None
    assert failure.category == "request_deadline"
    assert failure.input_bytes > 0
    assert stopped.is_set(), "the in-flight operation must be cancelled, not abandoned"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["plan", "analyze"])
async def test_partial_usage_is_not_reported_as_complete(operation):
    async def handler(request):
        content = {"tools": []} if operation == "plan" else {"summary": "ok", "claims": []}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 7},
            },
        )

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    response = await invoke(client, operation)
    assert response.usage_reported is False
    assert response.input_tokens == 7


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan")])
def test_invalid_request_deadline_is_rejected_before_any_call(seconds):
    with pytest.raises(ValueError):
        QwenCompatibleClient(api_key="test", timeout_seconds=seconds)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["agent", "plan", "analyze"])
async def test_deadline_while_waiting_for_capacity_has_no_invented_byte_measurement(operation):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(503)

    client = QwenCompatibleClient(
        api_key="test", transport=httpx.MockTransport(handler), timeout_seconds=0.02
    )
    # Hold the single slot to isolate queue time from transport time.
    await client._semaphore.acquire()
    try:
        with pytest.raises(ProviderError) as caught:
            await invoke(client, operation)
        assert caught.value.failure.category == "request_deadline"
        assert caught.value.failure.input_bytes is None
        assert requests == []
    finally:
        client._semaphore.release()


@pytest.mark.parametrize(
    "values",
    [
        {"category": "PRIVATE_EXCEPTION_TEXT"},
        {"category": "read_timeout", "input_bytes": -1},
        {"category": "read_timeout", "input_tokens": True},
        {"category": "http_error", "http_status": 600},
        {"category": "http_error", "http_status": "PRIVATE_RESPONSE"},
    ],
)
def test_failure_metadata_rejects_non_allowlisted_values(values):
    with pytest.raises(ValueError):
        ProviderFailure(**values)


def test_zero_usage_is_distinct_from_unknown_usage():
    measured = ProviderFailure(category="invalid_response", input_tokens=0, output_tokens=0)
    unknown = ProviderFailure(category="read_timeout")
    assert measured.as_payload()["input_tokens"] == 0
    assert unknown.as_payload()["input_tokens"] is None


@pytest.mark.asyncio
async def test_http_error_retains_valid_usage_without_retaining_response_body():
    async def handler(request):
        return httpx.Response(
            500,
            json={
                "error": "PRIVATE_RESPONSE_BODY",
                "usage": {"prompt_tokens": 17, "completion_tokens": 4},
            },
        )

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await invoke(client, "analyze")
    assert caught.value.failure.http_status == 500
    assert caught.value.failure.input_tokens == 17
    assert caught.value.failure.output_tokens == 4
    assert "PRIVATE_RESPONSE_BODY" not in json.dumps(caught.value.failure.as_payload())


@pytest.mark.asyncio
async def test_cancellation_at_response_completion_is_never_swallowed():
    caller = asyncio.current_task()

    async def handler(request):
        asyncio.get_running_loop().call_soon(caller.cancel)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"tools":[]}'}}]})

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(asyncio.CancelledError):
        await invoke(client, "plan")


@pytest.mark.asyncio
async def test_http_error_with_overdeep_json_retains_status_and_measured_bytes():
    async def handler(request):
        return httpx.Response(500, text="[" * 2000 + "0" + "]" * 2000)

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await invoke(client, "analyze")
    assert caught.value.failure.category == "http_error"
    assert caught.value.failure.http_status == 500
    assert caught.value.failure.input_bytes > 0
    assert caught.value.failure.input_tokens is None
    assert caught.value.failure.output_tokens is None
