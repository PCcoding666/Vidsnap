"""Allow-listed clients, request shapes and failure records, with no network."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.eval.helpers import make_item
from vidsnap.eval.adapters import FakeMedia
from vidsnap.eval.providers import (
    DASHSCOPE_BASE_URL,
    HARNESS_MODELS,
    NATIVE_MODELS,
    BailianChatClient,
    BailianNativeVideo,
    EvalAsrRecognizer,
    NativeRequest,
    endpoint_key,
    extract_json_object,
    usage_details,
)
from vidsnap.eval.systems import BuildOptions, NotApplicable, build_components, parse_system
from vidsnap.eval.tasks import get_task
from vidsnap.providers.base import ProviderError, ProviderUnavailable
from vidsnap.video.probe import MediaProbe

KEY = "test-key-not-a-real-credential"


def transport(handler: Any, seen: list[httpx.Request]) -> httpx.MockTransport:
    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        result: httpx.Response = handler(request)
        return result

    return httpx.MockTransport(record)


def test_json_extraction_tolerates_fences_and_prose() -> None:
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('好的，结果如下：{"a": {"b": 2}} 以上。') == {"a": {"b": 2}}
    assert extract_json_object("no json here") is None


def test_usage_details_are_renamed_so_redaction_keeps_them() -> None:
    details = usage_details(
        {
            "prompt_tokens_details": {"audio_tokens": 10, "video_tokens": 90, "cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 7},
        }
    )
    assert details == {
        "input_audio": 10,
        "input_video": 90,
        "input_cached": 0,
        "output_reasoning": 7,
    }
    assert not any("token" in key for key in details)


@pytest.mark.asyncio
async def test_json_mode_request_shape_and_usage() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"summary": "ok"}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    client = BailianChatClient(
        profile=HARNESS_MODELS["qwen3.8-max"],
        endpoint="dashscope",
        api_key=KEY,
        transport=transport(handler, seen),
    )
    completion = await client.complete([{"role": "user", "content": "hi"}], json_mode=True)
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == f"{DASHSCOPE_BASE_URL}/chat/completions"
    assert body["model"] == "qwen3.8-max"
    assert body["response_format"] == {"type": "json_object"}
    assert "stream" not in body
    assert completion.payload == {"summary": "ok"}
    assert completion.usage.input_tokens == 100 and completion.usage.reported


@pytest.mark.asyncio
async def test_streaming_omni_request_collects_content_and_usage() -> None:
    seen: list[httpx.Request] = []
    chunks = [
        {"choices": [{"delta": {"reasoning_content": "thinking..."}}]},
        {"choices": [{"delta": {"content": '{"summary": '}}]},
        {"choices": [{"delta": {"content": '"好"}'}}]},
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 500,
                "completion_tokens": 40,
                "prompt_tokens_details": {"audio_tokens": 50, "video_tokens": 440},
            },
        },
    ]
    stream = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})

    client = BailianChatClient(
        profile=NATIVE_MODELS["qwen3.8-omni-flash"],
        endpoint="dashscope",
        api_key=KEY,
        transport=transport(handler, seen),
    )
    completion = await client.complete([{"role": "user", "content": "hi"}], json_mode=False)
    body = json.loads(seen[0].content)
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert body["modalities"] == ["text"]
    assert "response_format" not in body
    assert completion.payload == {"summary": "好"}
    assert completion.usage.input_tokens == 500
    assert completion.details["input_audio"] == 50


@pytest.mark.asyncio
async def test_http_refusal_becomes_a_structured_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": "AccessDenied.Unpurchased"}})

    client = BailianChatClient(
        profile=HARNESS_MODELS["qwen3.8-max"],
        endpoint="token-plan",
        api_key=KEY,
        transport=transport(handler, []),
    )
    with pytest.raises(ProviderError) as raised:
        await client.complete([{"role": "user", "content": "hi"}], json_mode=True)
    failure = raised.value.failure
    assert failure is not None and failure.category == "http_4xx" and failure.http_status == 403


@pytest.mark.asyncio
async def test_missing_key_blocks_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("VIDSNAP_DASHSCOPE_API_KEY", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert endpoint_key("dashscope") is None
    seen: list[httpx.Request] = []
    client = BailianChatClient(
        profile=NATIVE_MODELS["qwen3.8-omni-flash"],
        endpoint="dashscope",
        api_key=None,
        transport=transport(lambda request: httpx.Response(200), seen),
    )
    with pytest.raises(ProviderUnavailable):
        await client.complete([], json_mode=False)
    assert seen == []


def test_models_are_pinned_to_their_endpoints() -> None:
    with pytest.raises(ValueError):
        BailianChatClient(
            profile=NATIVE_MODELS["qwen3.8-omni-flash"], endpoint="token-plan", api_key=KEY
        )


@pytest.mark.asyncio
async def test_native_video_is_sent_whole_as_base64(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42small-video")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"x": 1}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    native = BailianNativeVideo(
        BailianChatClient(
            profile=NATIVE_MODELS["qwen3.8-max"],
            endpoint="dashscope",
            api_key=KEY,
            transport=transport(handler, seen),
        )
    )
    probe = MediaProbe(duration_seconds=10, fps=25, width=640, height=360, has_audio=True)
    completion = await native.analyze_video(
        NativeRequest(
            task=get_task("t2b"),
            item=make_item(),
            prompt="任务提示",
            video=video,
            probe=probe,
            work_dir=tmp_path / "work",
        )
    )
    content = json.loads(seen[0].content)["messages"][0]["content"]
    assert content[0]["type"] == "video_url"
    encoded = content[0]["video_url"]["url"].removeprefix("data:;base64,")
    assert base64.b64decode(encoded) == video.read_bytes()
    assert content[1] == {"type": "text", "text": "任务提示"}
    assert completion.details["transcoded"] is False
    assert completion.details["sent_bytes"] == video.stat().st_size


@pytest.mark.asyncio
async def test_asr_keeps_the_released_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "转写文本"}}]})

    recognizer = EvalAsrRecognizer(api_key=KEY, transport=transport(handler, seen))
    response = await recognizer.transcribe(b"RIFFfake-wav", mime_type="audio/wav")
    body = json.loads(seen[0].content)
    assert body["model"] == "qwen3-asr-flash"
    part = body["messages"][0]["content"][0]
    assert part["type"] == "input_audio" and part["input_audio"].startswith(
        "data:audio/wav;base64,"
    )
    assert response.text == "转写文本"
    assert not response.usage.reported


@pytest.mark.asyncio
async def test_asr_sends_compressed_audio_whole_with_its_real_mime_type() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "转写文本"}}]})

    recognizer = EvalAsrRecognizer(api_key=KEY, transport=transport(handler, seen))
    audio = b"\xff\xfb" * 3_700_000  # 7.4 MB: over the 7 MB WAV chunk size, under 10 MB of Base64

    assert recognizer.accepts_compressed_audio is True
    response = await recognizer.transcribe(audio, mime_type="audio/mpeg")

    assert len(seen) == 1 and response.usage.model_calls == 1
    uri = json.loads(seen[0].content)["messages"][0]["content"][0]["input_audio"]
    assert uri.startswith("data:audio/mpeg;base64,")
    assert base64.b64decode(uri.removeprefix("data:audio/mpeg;base64,")) == audio


def test_system_names_are_allow_listed() -> None:
    assert parse_system("harness+qwen3.8-max+oracle-asr+frame-labels").name == (
        "harness+qwen3.8-max+oracle-asr+frame-labels"
    )
    assert parse_system("native:qwen3.8-omni-flash").kind == "native"
    for bad in ("harness+gpt-5", "native:any-model", "harness+qwen3.8-max+fast", "direct:x"):
        with pytest.raises(ValueError):
            parse_system(bad)
    assert parse_system("harness+qwen3.8-max+oracle-frames").base_name == "harness+qwen3.8-max"


def test_oracles_need_references() -> None:
    item = make_item(reference={})
    media = FakeMedia(duration_seconds=10, has_audio=True)
    for name in ("harness+mock+oracle-asr", "harness+mock+oracle-frames"):
        with pytest.raises(NotApplicable):
            build_components(
                parse_system(name), get_task("t1"), item, media=media, options=BuildOptions()
            )
