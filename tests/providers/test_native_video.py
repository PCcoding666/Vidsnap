"""Offline MockTransport boundary tests for the Bailian native audiovisual port."""

import asyncio
import base64
import json
import pathlib
from pathlib import Path

import httpx
import pytest

from vidsnap.providers.base import ProviderIdentity
from vidsnap.providers.native_video import (
    MAX_CONTENT_BYTES,
    MAX_INLINE_BASE64_BYTES,
    NativeClip,
    NativeVideoClient,
    NativeVideoError,
)

TASK = "输出该片段忠实于来源的中文notes与简短summary。"


def _sse(events: list[dict[str, object]], *, done: bool = True) -> bytes:
    lines = [f"data: {json.dumps(event)}\n\n" for event in events]
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _text_delta(text: str, **extra: object) -> dict[str, object]:
    delta: dict[str, object] = {"role": "assistant", "content": text}
    delta.update(extra)
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]}


def _stop_chunk() -> dict[str, object]:
    return {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}


def _ok_stream(*, usage: dict[str, object] | None = None) -> bytes:
    events: list[dict[str, object]] = [_text_delta("你好"), _text_delta("，世界"), _stop_chunk()]
    if usage is not None:
        events.append({"usage": usage})
    return _sse(events)


def _write_mkv(tmp_path: Path, payload: bytes = b"fake-mkv-bytes") -> Path:
    clip_path = tmp_path / "clip.mkv"
    clip_path.write_bytes(payload)
    return clip_path


def _clip(clip_path: Path) -> NativeClip:
    return NativeClip(
        path=clip_path,
        mime_type="video/x-matroska",
        duration_seconds=119.0,
        sha256="a" * 64,
    )


def _client(handler, tmp_path: Path, **overrides: object) -> NativeVideoClient:
    options: dict[str, object] = {
        "api_key": "test-key",
        "max_video_bytes": 1024,
        "transport": httpx.MockTransport(handler),
    }
    options.update(overrides)
    return NativeVideoClient(**options)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_native_video_sends_exact_model_and_video_payload(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_ok_stream(usage={"prompt_tokens": 10, "completion_tokens": 5}),
        )

    clip_path = _write_mkv(tmp_path)
    client = _client(handler, tmp_path)

    result = await client.analyze_clip(_clip(clip_path), task=TASK)

    assert result.text == "你好，世界"
    assert len(captured) == 1
    request = captured[0]
    assert request.url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "qwen3.5-omni-plus"
    expected_video = base64.b64encode(clip_path.read_bytes()).decode("ascii")
    assert body == {
        "model": "qwen3.5-omni-plus",
        "modalities": ["text"],
        "max_tokens": 4096,
        "stream": True,
        "stream_options": {"include_usage": True},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {"url": f"data:video/x-matroska;base64,{expected_video}"},
                    },
                    {"type": "text", "text": TASK},
                ],
            }
        ],
    }
    assert result.request_bytes == len(request.content)
    assert result.usage.reported is True
    assert result.usage.model_calls == 1
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.usage.input_bytes == len(request.content)
    assert result.identity == ProviderIdentity(
        id="bailian-native-video",
        model="qwen3.5-omni-plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


@pytest.mark.asyncio
async def test_native_video_reports_unknown_usage_when_stream_omits_it(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_ok_stream(),
        )

    result = await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)

    assert result.text == "你好，世界"
    assert result.usage.reported is False
    assert result.usage.model_calls == 1
    assert result.usage.input_bytes > 0


@pytest.mark.asyncio
async def test_native_video_partial_usage_is_not_claimed_as_known(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_ok_stream(usage={"prompt_tokens": 7}),
        )

    result = await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)

    assert result.usage.reported is False
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0


@pytest.mark.asyncio
async def test_native_video_does_not_persist_reasoning(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        events = [
            _text_delta("", reasoning_content="hidden chain"),
            _text_delta("visible notes"),
            _stop_chunk(),
            {"usage": {"prompt_tokens": 3, "completion_tokens": 2}},
        ]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(events),
        )

    result = await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)

    assert result.text == "visible notes"
    assert "hidden chain" not in result.text
    assert not hasattr(result, "reasoning")


@pytest.mark.asyncio
async def test_native_video_rejects_oversize_clip_before_any_request(tmp_path: Path) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_ok_stream())

    client = _client(handler, tmp_path, max_video_bytes=4)

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert calls == 0
    assert excinfo.value.category == "oversize"
    assert excinfo.value.attempts == 0
    assert excinfo.value.request_bytes == 0


@pytest.mark.asyncio
async def test_native_video_rejects_oversize_base64_encoding(tmp_path: Path) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_ok_stream())

    assert MAX_INLINE_BASE64_BYTES == 10_000_000
    # 8 raw bytes encode to a 12-byte base64 string, over the test cap of 10.
    client = _client(handler, tmp_path, base64_max_bytes=10)

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert calls == 0
    assert excinfo.value.category == "oversize"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "http_500",
        "connect_error",
        "truncated_stream",
        "invalid_event",
        "length_finish",
        "sse_error_event",
        "no_stop_finish",
    ],
)
async def test_native_video_fails_once_without_retry(tmp_path: Path, failure: str) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure == "http_500":
            return httpx.Response(500, json={"error": {"message": "boom"}})
        if failure == "connect_error":
            raise httpx.ConnectError("offline", request=request)
        if failure == "truncated_stream":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse([_text_delta("partial"), _stop_chunk()], done=False),
            )
        if failure == "invalid_event":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b"data: {not-json\n\n",
            )
        if failure == "length_finish":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse(
                    [
                        _text_delta("cut off"),
                        {"choices": [{"index": 0, "delta": {}, "finish_reason": "length"}]},
                    ]
                ),
            )
        if failure == "sse_error_event":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse([{"error": {"message": "model exploded"}}]),
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse([_text_delta("no stop marker")]),
        )

    with pytest.raises(NativeVideoError) as excinfo:
        await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert calls == 1
    assert excinfo.value.attempts == 1


@pytest.mark.asyncio
async def test_native_video_failure_carries_safe_metadata_without_body(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"message": "upstream raw detail SECRET-MARKER-123"}},
        )

    client = _client(handler, tmp_path)

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    error = excinfo.value
    assert error.category == "http_error"
    assert error.http_status == 503
    assert error.attempts == 1
    assert error.request_bytes > 0
    assert not hasattr(error, "body")
    assert not hasattr(error, "response_body")


@pytest.mark.asyncio
async def test_native_video_network_failure_metadata(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(NativeVideoError) as excinfo:
        await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    error = excinfo.value
    assert error.category == "network_error"
    assert error.http_status is None
    assert error.attempts == 1
    assert error.request_bytes > 0


@pytest.mark.asyncio
async def test_native_video_error_never_echoes_raw_content_or_credentials(
    tmp_path: Path,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "rejected raw clip bytes SECRET-MARKER-123"}},
        )

    client = _client(handler, tmp_path, api_key="test-key")

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    message = str(excinfo.value)
    assert "SECRET-MARKER-123" not in message
    assert "test-key" not in message
    assert "rejected raw clip bytes" not in message


@pytest.mark.asyncio
async def test_native_video_requires_local_key(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent without a key")

    client = _client(handler, tmp_path, api_key=None)

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert excinfo.value.category == "unavailable"
    assert excinfo.value.attempts == 0


@pytest.mark.asyncio
async def test_native_video_sends_json_content_type(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=_ok_stream())

    await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)

    assert captured[0].headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_native_video_payload_fixes_max_tokens(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, content=_ok_stream())

    await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)

    assert json.loads(captured[0].content)["max_tokens"] == 4096


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "deltas",
    [[], ["   ", "\n", "\t"]],
    ids=["no_content", "whitespace_only"],
)
async def test_native_video_blank_final_text_is_failure(tmp_path: Path, deltas: list[str]) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        events: list[dict[str, object]] = [_text_delta(part) for part in deltas]
        events.append(_stop_chunk())
        return httpx.Response(200, content=_sse(events))

    with pytest.raises(NativeVideoError) as excinfo:
        await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert calls == 1
    assert excinfo.value.attempts == 1


@pytest.mark.asyncio
async def test_native_video_stream_deadline_is_overall_not_per_chunk(tmp_path: Path) -> None:
    calls = 0

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            for _ in range(10):
                yield f"data: {json.dumps(_text_delta('你'))}\n\n".encode()
                await asyncio.sleep(0.03)

        async def aclose(self) -> None:
            return None

    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=SlowStream(),
                request=request,
            )

    # Each chunk arrives well under any per-chunk read timeout, but the whole
    # stream runs past the 0.1s overall deadline.
    client = _client(
        handler=None, tmp_path=tmp_path, timeout_seconds=0.1, transport=SlowTransport()
    )

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert calls == 1
    assert excinfo.value.category == "timeout"
    assert excinfo.value.attempts == 1


@pytest.mark.asyncio
async def test_native_video_accumulated_content_cap_is_enforced(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        events = [_text_delta("你好世界你好世界"), _stop_chunk()]
        return httpx.Response(200, content=_sse(events))

    client = _client(handler, tmp_path, max_content_bytes=16)

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert excinfo.value.attempts == 1


@pytest.mark.asyncio
async def test_native_video_content_cap_cannot_be_enlarged(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        events = [_text_delta("字" * 200_000) for _ in range(6)]
        events.append(_stop_chunk())
        return httpx.Response(200, content=_sse(events))

    assert MAX_CONTENT_BYTES == 1_000_000
    client = _client(handler, tmp_path, max_content_bytes=10**12)

    with pytest.raises(NativeVideoError):
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)


@pytest.mark.asyncio
async def test_native_video_base64_hard_cap_cannot_be_enlarged(tmp_path: Path) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_ok_stream())

    # 7_500_001 raw bytes encode to exactly 10_000_004 base64 chars, past the cap.
    clip_path = _write_mkv(tmp_path, b"x" * 7_500_001)
    client = _client(handler, tmp_path, max_video_bytes=10**12, base64_max_bytes=10**12)

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(clip_path), task=TASK)
    assert calls == 0
    assert excinfo.value.category == "oversize"


@pytest.mark.asyncio
async def test_native_video_oversize_rejected_without_reading_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = 0
    real_read_bytes = pathlib.Path.read_bytes

    def counting_read_bytes(self: pathlib.Path) -> bytes:
        nonlocal reads
        reads += 1
        return real_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", counting_read_bytes)
    client = _client(None, tmp_path, max_video_bytes=4)

    with pytest.raises(NativeVideoError) as excinfo:
        await client.analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert excinfo.value.category == "oversize"
    assert reads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["connect_error", "invalid_event"])
async def test_native_video_error_cause_does_not_expose_underlying_error(
    tmp_path: Path, failure: str
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if failure == "connect_error":
            raise httpx.ConnectError("dial raw SECRET-MARKER-123", request=request)
        return httpx.Response(200, content=b"data: {not-json\n\n")

    with pytest.raises(NativeVideoError) as excinfo:
        await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": True, "completion_tokens": 5},
        {"prompt_tokens": 10, "completion_tokens": False},
        {"prompt_tokens": -1, "completion_tokens": 5},
        {"prompt_tokens": 10, "completion_tokens": -3},
    ],
    ids=["bool_prompt", "bool_completion", "negative_prompt", "negative_completion"],
)
async def test_native_video_rejects_bool_or_negative_token_usage(
    tmp_path: Path, usage: dict[str, object]
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ok_stream(usage=usage))

    result = await _client(handler, tmp_path).analyze_clip(_clip(_write_mkv(tmp_path)), task=TASK)

    assert result.usage.reported is False
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0
