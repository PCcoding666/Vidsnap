"""The native DashScope ``qwen-audio-3.1-asr-flash`` request and response, offline.

Every reply is a recorded or synthetic JSON document served by ``httpx.MockTransport``;
no audio is read, no network is used and no key is real.
"""

from __future__ import annotations

import base64
import json
import struct
from typing import Any

import httpx
import pytest

from tests.fixtures.native_asr import (
    ASR_URL,
    RECORDED_TEXT,
    audio_part,
    native_reply,
    recorded_response,
)
from vidsnap.contracts.failures import ProviderFailure
from vidsnap.providers.asr import (
    QWEN_ASR_IDENTITY,
    QWEN_ASR_MODEL,
    AsrTranscript,
    Base64AudioChunker,
    QwenAsrRecognizer,
    QwenAudioAsrClient,
)
from vidsnap.providers.base import ProviderError, ProviderUnavailable

_CREDENTIAL = "asr-credential-for-tests"


def _recording_client(
    replies: list[httpx.Response] | None = None,
    *,
    chunker: Base64AudioChunker | None = None,
) -> tuple[QwenAudioAsrClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(replies or [])

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if queue else httpx.Response(200, json=native_reply("heard"))

    client = QwenAudioAsrClient(
        api_key=_CREDENTIAL, chunker=chunker, transport=httpx.MockTransport(handler)
    )
    return client, seen


def _reply(text: str, duration: int, input_tokens: int, output_tokens: int) -> dict[str, Any]:
    return native_reply(
        text, duration=duration, input_tokens=input_tokens, output_tokens=output_tokens
    )


def _wav(pcm: bytes, *, sample_rate: int = 16_000) -> bytes:
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        len(pcm),
    )
    return header + pcm


def test_the_model_and_endpoint_are_the_native_audio_model() -> None:
    assert QWEN_ASR_MODEL == "qwen-audio-3.1-asr-flash"
    assert QWEN_ASR_IDENTITY.model == QWEN_ASR_MODEL
    assert ASR_URL.startswith(QWEN_ASR_IDENTITY.base_url + "/")


@pytest.mark.asyncio
async def test_request_is_the_native_message_shape_with_only_the_key_header() -> None:
    client, seen = _recording_client()
    audio = b"ID3\x04\x00" + bytes(range(64))

    await client.recognize(audio, mime_type="audio/mpeg")

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == ASR_URL
    assert request.headers["Authorization"] == f"Bearer {_CREDENTIAL}"
    assert request.headers["Content-Type"] == "application/json"
    body = json.loads(request.content)
    assert set(body) == {"model", "input", "parameters"}
    assert body["model"] == "qwen-audio-3.1-asr-flash"
    assert audio_part(body) == {
        "type": "input_audio",
        "input_audio": {"data": f"data:audio/mpeg;base64,{base64.b64encode(audio).decode()}"},
    }
    assert body["parameters"] == {"format": "mp3", "sample_rate": "16000"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime_type", "audio_format", "data_uri_mime"),
    [
        ("audio/mpeg", "mp3", "audio/mpeg"),
        ("audio/mp3", "mp3", "audio/mpeg"),
        ("AUDIO/MPEG; charset=binary", "mp3", "audio/mpeg"),
        ("audio/aac", "aac", "audio/aac"),
        ("audio/wav", "wav", "audio/wav"),
        ("audio/x-wav", "wav", "audio/wav"),
        ("audio/wave", "wav", "audio/wav"),
        ("audio/vnd.wave", "wav", "audio/wav"),
    ],
)
async def test_parameters_format_and_data_uri_follow_the_real_mime_type(
    mime_type: str, audio_format: str, data_uri_mime: str
) -> None:
    client, seen = _recording_client()

    await client.recognize(b"abcd", mime_type=mime_type)

    body = json.loads(seen[0].content)
    assert body["parameters"]["format"] == audio_format
    assert audio_part(body)["input_audio"]["data"] == f"data:{data_uri_mime};base64,YWJjZA=="


@pytest.mark.asyncio
@pytest.mark.parametrize("mime_type", ["audio/flac", "audio/mp4", "video/mp4", "", "mp3"])
async def test_an_unknown_mime_type_is_refused_before_any_request(mime_type: str) -> None:
    client, seen = _recording_client()

    with pytest.raises(ProviderError, match="MIME") as excinfo:
        await client.recognize(b"abcd", mime_type=mime_type)

    assert seen == []
    failure = excinfo.value.failure
    assert isinstance(failure, ProviderFailure) and failure.category == "validation"


@pytest.mark.asyncio
async def test_sample_rate_is_16000_for_compressed_audio_and_the_header_rate_for_wav() -> None:
    client, seen = _recording_client()

    await client.recognize(b"\xff\xfb" * 8, mime_type="audio/mpeg")
    await client.recognize(b"junk", mime_type="audio/wav")  # not a parsable WAV
    await client.recognize(_wav(bytes(64), sample_rate=8_000), mime_type="audio/wav")
    await client.recognize(_wav(bytes(64)), mime_type="audio/wav")

    rates = [json.loads(request.content)["parameters"]["sample_rate"] for request in seen]
    assert rates == ["16000", "16000", "8000", "16000"]


@pytest.mark.asyncio
async def test_language_hints_are_omitted_so_the_model_detects_the_language() -> None:
    client, seen = _recording_client()

    await client.recognize(b"abcd")

    parameters = json.loads(seen[0].content)["parameters"]
    assert "language_hints" not in parameters
    assert set(parameters) == {"format", "sample_rate"}


@pytest.mark.asyncio
async def test_the_recorded_reply_gives_text_and_usage() -> None:
    client, _ = _recording_client([httpx.Response(200, json=recorded_response())])

    transcript = await client.recognize(b"abcd", mime_type="audio/mpeg")

    assert transcript == AsrTranscript(
        text=RECORDED_TEXT,
        requests=1,
        audio_seconds=7,
        input_tokens=182,
        output_tokens=19,
    )
    assert transcript.usage_reported is True


@pytest.mark.asyncio
async def test_the_recorded_reply_through_the_recognizer_is_plain_text() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=recorded_response()))
    recognizer = QwenAsrRecognizer(api_key=_CREDENTIAL, transport=transport)

    assert await recognizer.transcribe(b"abcd", mime_type="audio/mpeg") == RECORDED_TEXT


@pytest.mark.asyncio
async def test_text_falls_back_to_the_sentence_text_when_output_text_is_absent() -> None:
    reply = {"output": {"sentence": {"text": "from the sentence"}}, "usage": {"duration": 3}}
    client, _ = _recording_client([httpx.Response(200, json=reply)])

    transcript = await client.recognize(b"abcd")

    assert transcript.text == "from the sentence"
    assert transcript.audio_seconds == 3
    assert transcript.usage_reported is False  # no token counters in this reply


@pytest.mark.asyncio
async def test_empty_text_is_a_valid_empty_transcript() -> None:
    client, _ = _recording_client([httpx.Response(200, json=native_reply(""))])

    assert (await client.recognize(b"abcd")).text == ""


@pytest.mark.asyncio
async def test_usage_may_sit_under_output_when_the_top_level_has_none() -> None:
    reply = {
        "output": {
            "text": "x",
            "usage": {"duration": 2, "input_tokens": 60, "output_tokens": 4},
        }
    }
    client, _ = _recording_client([httpx.Response(200, json=reply)])

    transcript = await client.recognize(b"abcd")

    assert (transcript.audio_seconds, transcript.input_tokens, transcript.output_tokens) == (
        2,
        60,
        4,
    )


@pytest.mark.asyncio
async def test_unusable_counters_are_unreported_not_zero() -> None:
    reply = native_reply("x")
    reply["usage"] = {"duration": "7", "input_tokens": True, "output_tokens": -1}
    client, _ = _recording_client([httpx.Response(200, json=reply)])

    transcript = await client.recognize(b"abcd")

    assert transcript.text == "x"
    assert (transcript.audio_seconds, transcript.input_tokens, transcript.output_tokens) == (
        None,
        None,
        None,
    )
    assert transcript.usage_reported is False


@pytest.mark.asyncio
async def test_a_wav_cut_into_pieces_sends_one_request_each_and_adds_the_usage() -> None:
    pcm = bytes(1000)
    client, seen = _recording_client(
        [
            httpx.Response(
                200, json=native_reply("a", duration=3, input_tokens=70, output_tokens=2)
            ),
            httpx.Response(
                200, json=native_reply("b", duration=2, input_tokens=50, output_tokens=3)
            ),
        ],
        chunker=Base64AudioChunker(chunk_bytes=600),
    )

    transcript = await client.recognize(_wav(pcm))

    assert len(seen) == 2
    assert transcript == AsrTranscript(
        text="a\nb", requests=2, audio_seconds=5, input_tokens=120, output_tokens=5
    )


@pytest.mark.asyncio
async def test_one_chunk_without_counters_makes_the_total_unreported() -> None:
    client, _ = _recording_client(
        [
            httpx.Response(200, json=native_reply("a", duration=3)),
            httpx.Response(200, json=native_reply("b", duration=None, input_tokens=None)),
        ],
        chunker=Base64AudioChunker(chunk_bytes=600),
    )

    transcript = await client.recognize(_wav(bytes(1000)))

    assert transcript.text == "a\nb"
    assert transcript.audio_seconds is None
    assert transcript.usage_reported is False


@pytest.mark.asyncio
async def test_no_audio_means_no_request_and_an_empty_transcript() -> None:
    client, seen = _recording_client()

    assert await client.recognize(b"") == AsrTranscript(text="", requests=0)
    assert seen == []


@pytest.mark.asyncio
async def test_unsupported_format_is_a_categorized_failure_that_leaks_nothing() -> None:
    reply = {
        "request_id": "sentinel-request-id-7c1d",
        "code": "UNSUPPORTED_FORMAT",
        "message": "format is empty sentinel-body-text-0f3e",
    }
    client, _ = _recording_client([httpx.Response(400, json=reply)])

    with pytest.raises(ProviderError) as excinfo:
        await client.recognize(b"abcd", mime_type="audio/mpeg")

    failure = excinfo.value.failure
    assert isinstance(failure, ProviderFailure)
    assert (failure.category, failure.http_status) == ("http_4xx", 400)
    serialized = json.dumps(failure.as_payload()) + str(excinfo.value)
    for marker in (
        "UNSUPPORTED_FORMAT",
        "format is empty",
        "sentinel-body-text-0f3e",
        "sentinel-request-id-7c1d",
        _CREDENTIAL,
        "dashscope",
        "https://",
        "Bearer",
        "abcd",
    ):
        assert marker not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [
        {"output": {}, "usage": {"duration": 1}},
        {"output": {"text": None}},
        {"output": {"text": 7}},
        {"output": {"sentence": {"text": 7}}},
        {"output": "text"},
        {"output": None},
        {"choices": [{"message": {"content": "OpenAI-shaped reply"}}]},
        {"code": "InvalidParameter", "message": "bad request"},
        ["not", "an", "object"],
    ],
)
async def test_a_reply_without_text_is_an_invalid_response(reply: Any) -> None:
    client, _ = _recording_client([httpx.Response(200, json=reply)])

    with pytest.raises(ProviderError) as excinfo:
        await client.recognize(b"abcd")

    failure = excinfo.value.failure
    assert isinstance(failure, ProviderFailure) and failure.category == "invalid_response"


@pytest.mark.asyncio
async def test_a_reply_that_is_not_json_is_an_invalid_response() -> None:
    client, _ = _recording_client([httpx.Response(200, content=b"<html>gateway</html>")])

    with pytest.raises(ProviderError) as excinfo:
        await client.recognize(b"abcd")

    failure = excinfo.value.failure
    assert isinstance(failure, ProviderFailure) and failure.category == "invalid_response"


@pytest.mark.asyncio
async def test_without_a_key_the_client_is_blocked_before_any_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent without a key")

    client = QwenAudioAsrClient(api_key=None, transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderUnavailable):
        await client.recognize(b"abcd")


def test_the_client_rejects_a_timeout_that_is_not_positive() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        QwenAudioAsrClient(api_key=_CREDENTIAL, timeout_seconds=0)
