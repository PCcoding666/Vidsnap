"""Offline tests for strict partial-usage accounting on Qwen and native video paths."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from vidsnap.contracts import Evidence, VideoGoal
from vidsnap.providers.base import AgentStepRequest
from vidsnap.providers.native_video import NativeClip, NativeVideoClient, NativeVideoError
from vidsnap.providers.qwen import QwenCompatibleClient
from vidsnap.video.probe import MediaProbe

_TASK = "输出该片段忠实于来源的中文notes与简短summary。"


def _decision_payload(usage: object) -> dict[str, object]:
    decision = {
        "kind": "tool_calls",
        "calls": [{"name": "sample_evidence", "arguments": {"max_frames": 1}}],
    }
    return {
        "choices": [{"message": {"content": json.dumps(decision)}}],
        "usage": usage,
    }


def _step_request() -> AgentStepRequest:
    return AgentStepRequest(
        goal=VideoGoal(objective="检查partial usage的严格计量"),
        probe=MediaProbe(duration_seconds=30, fps=24, width=640, height=360, has_audio=False),
        evidence=(
            Evidence(
                id="e1",
                start_seconds=0.0,
                end_seconds=10.0,
                modality="transcript",
                content="样例文本",
            ),
        ),
        tool_results=(),
        tool_schemas=({"name": "sample_evidence", "input_schema": {"type": "object"}},),
        output_schema={"type": "object"},
        remaining_model_calls=10,
        remaining_tool_calls=5,
        remaining_frames=50,
    )


async def _decide_with_usage(usage: object) -> tuple[object, int]:
    captured_bytes: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_bytes.append(len(request.content))
        return httpx.Response(200, json=_decision_payload(usage))

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    response = await client.decide_next(_step_request())
    return response.usage, captured_bytes[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": 7},
        {"completion_tokens": 3},
        {"prompt_tokens": 7, "completion_tokens": None},
        {"prompt_tokens": True, "completion_tokens": 3},
        {"prompt_tokens": 7, "completion_tokens": False},
        {"prompt_tokens": -1, "completion_tokens": 3},
        {"prompt_tokens": 7, "completion_tokens": -2},
        {"prompt_tokens": "7", "completion_tokens": 3},
        {"prompt_tokens": 7.5, "completion_tokens": 3},
    ],
)
async def test_qwen_agent_decision_partial_or_invalid_usage_stays_unreported(
    usage: object,
) -> None:
    """Partial/bool/negative/bad-typed token counts must never be reported as 0."""
    usage_result, request_bytes = await _decide_with_usage(usage)

    assert usage_result.reported is False
    assert usage_result.input_tokens == 0
    assert usage_result.output_tokens == 0
    assert usage_result.model_calls == 1
    assert usage_result.input_bytes == request_bytes


@pytest.mark.asyncio
async def test_qwen_agent_decision_complete_usage_still_reported() -> None:
    usage_result, request_bytes = await _decide_with_usage(
        {"prompt_tokens": 7, "completion_tokens": 3}
    )

    assert usage_result.reported is True
    assert usage_result.input_tokens == 7
    assert usage_result.output_tokens == 3
    assert usage_result.model_calls == 1
    assert usage_result.input_bytes == request_bytes


def _sse_lines(*chunks: str) -> bytes:
    return "".join(f"data: {chunk}\n\n" for chunk in chunks).encode("utf-8")


def _usage_event(prompt: int, completion: int) -> str:
    return json.dumps({"usage": {"prompt_tokens": prompt, "completion_tokens": completion}})


def _text_event(text: str) -> str:
    return json.dumps(
        {
            "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}
            ]
        }
    )


def _stop_event() -> str:
    return json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})


def _clip(tmp_path: Path) -> NativeClip:
    clip_path = tmp_path / "clip.mkv"
    clip_path.write_bytes(b"fake-mkv-bytes")
    return NativeClip(
        path=clip_path,
        mime_type="video/x-matroska",
        duration_seconds=119.0,
        sha256="a" * 64,
    )


def _client(handler, **overrides: object) -> NativeVideoClient:
    options: dict[str, object] = {
        "api_key": "test-key",
        "max_video_bytes": 1024,
        "transport": httpx.MockTransport(handler),
    }
    options.update(overrides)
    return NativeVideoClient(**options)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_native_stream_error_after_complete_usage_preserves_real_counts(
    tmp_path: Path,
) -> None:
    """Usage 7/3 observed before a missing [DONE] must survive on the error."""
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_lines(_text_event("你好"), _stop_event(), _usage_event(7, 3)),
        )

    client = _client(handler)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    error = exc_info.value
    assert error.category == "stream_error"
    assert error.attempts == 1
    assert len(captured) == 1
    usage = error.usage
    assert usage is not None
    assert usage.reported is True
    assert usage.model_calls == 1
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    assert usage.input_bytes == len(captured[0].content)


@pytest.mark.asyncio
async def test_native_invalid_stream_after_usage_preserves_real_counts(tmp_path: Path) -> None:
    """An invalid event after complete usage must keep 7/3 on the error."""
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_lines(_usage_event(7, 3), "not-json-at-all"),
        )

    client = _client(handler)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    usage = exc_info.value.usage
    assert usage is not None
    assert usage.reported is True
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    assert usage.input_bytes == len(captured[0].content)
    assert len(captured) == 1  # no retry


@pytest.mark.asyncio
async def test_native_stream_error_without_usage_defaults_to_none(tmp_path: Path) -> None:
    """No complete usage observed before failure means usage stays None."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_lines(_text_event("你好")),
        )

    client = _client(handler)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    assert exc_info.value.usage is None


class _DisconnectStream(httpx.AsyncByteStream):
    """Yields the usage bytes, then drops the connection."""

    def __init__(self, prefix: bytes) -> None:
        self._prefix = prefix

    async def __aiter__(self):
        yield self._prefix
        raise httpx.ReadError("connection dropped")

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_native_network_disconnect_after_usage_preserves_real_counts(
    tmp_path: Path,
) -> None:
    """A mid-stream network drop keeps observed usage; nothing is fabricated."""
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_DisconnectStream(_sse_lines(_text_event("你好"), _usage_event(7, 3))),
        )

    client = _client(handler)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    error = exc_info.value
    assert error.category == "network_error"
    usage = error.usage
    assert usage is not None
    assert usage.reported is True
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    assert usage.input_bytes == len(captured[0].content)


@pytest.mark.asyncio
async def test_native_error_usage_never_leaks_raw_stream_data(tmp_path: Path) -> None:
    """The error object carries only safe counters, never raw chunks or bodies."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_lines(_text_event("秘密内容"), _usage_event(7, 3), "garbage"),
        )

    client = _client(handler)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    error = exc_info.value
    public_attrs = {"category", "http_status", "request_bytes", "attempts", "usage", "args"}
    leaked = [name for name in vars(error) if name not in public_attrs]
    assert leaked == []
    assert "秘密内容" not in str(error)
    assert "秘密内容" not in repr(error.usage)


@pytest.mark.asyncio
async def test_native_unrelated_error_categories_keep_usage_none(tmp_path: Path) -> None:
    """Backward compatibility: existing error categories default usage to None."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"server error")

    client = _client(handler)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    assert exc_info.value.category == "http_error"
    assert exc_info.value.usage is None


@pytest.mark.asyncio
async def test_native_content_budget_error_after_usage_preserves_real_counts(
    tmp_path: Path,
) -> None:
    """Exceeding the text budget after observed usage must keep 7/3 on the error."""
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_lines(_usage_event(7, 3), _text_event("超" * 64)),
        )

    client = _client(handler, max_content_bytes=16)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    error = exc_info.value
    assert error.category == "stream_error"
    assert error.attempts == 1
    assert len(captured) == 1
    usage = error.usage
    assert usage is not None
    assert usage.reported is True
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    assert usage.input_bytes == len(captured[0].content)


@pytest.mark.asyncio
async def test_native_empty_text_error_after_usage_preserves_real_counts(
    tmp_path: Path,
) -> None:
    """A completed stream with no text after observed usage must keep 7/3."""
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_lines(_usage_event(7, 3), _stop_event(), "[DONE]"),
        )

    client = _client(handler)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    error = exc_info.value
    assert error.category == "stream_error"
    assert len(captured) == 1
    usage = error.usage
    assert usage is not None
    assert usage.reported is True
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    assert usage.input_bytes == len(captured[0].content)


@pytest.mark.asyncio
async def test_native_timeout_after_usage_preserves_real_counts(tmp_path: Path) -> None:
    """A deadline hit after observed usage keeps the real counts."""

    class _StallStream(httpx.AsyncByteStream):
        def __init__(self, prefix: bytes) -> None:
            self._prefix = prefix

        async def __aiter__(self):
            yield self._prefix
            await asyncio.sleep(30)

        async def aclose(self) -> None:
            return None

    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_StallStream(_sse_lines(_usage_event(7, 3))),
        )

    client = _client(handler, timeout_seconds=0.05)
    with pytest.raises(NativeVideoError) as exc_info:
        await client.analyze_clip(_clip(tmp_path), task=_TASK)

    error = exc_info.value
    assert error.category == "timeout"
    usage = error.usage
    assert usage is not None
    assert usage.reported is True
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    assert usage.input_bytes == len(captured[0].content)
