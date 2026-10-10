"""Local-only ASR request construction."""

import base64
import json

import httpx
import pytest

from tests.fixtures.native_asr import ASR_URL, native_reply
from vidsnap.config import DASHSCOPE_ASR_BASE_URL, TOKEN_PLAN_BASE_URL
from vidsnap.contracts.failures import ProviderFailure
from vidsnap.providers.asr import (
    QWEN_ASR_IDENTITY,
    Base64AudioChunker,
    QwenAsrRecognizer,
)
from vidsnap.providers.base import ProviderError, ProviderUnavailable

_ASR_CREDENTIAL = "asr-credential-for-tests"
_ASR_URL = ASR_URL


def test_asr_chunker_keeps_audio_in_memory_and_base64_encodes_chunks() -> None:
    # Audio that fits is one chunk, unchanged. Larger audio is split only as a valid
    # standalone file (see test_asr_chunking.py), never as raw byte slices.
    chunks = Base64AudioChunker(chunk_bytes=8).encode(b"abcdefgh")

    assert [chunk.index for chunk in chunks] == [0]
    assert [chunk.data_base64 for chunk in chunks] == [
        base64.b64encode(b"abcdefgh").decode("ascii"),
    ]


@pytest.mark.asyncio
async def test_qwen_asr_uses_an_in_memory_base64_data_uri() -> None:
    captured: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=native_reply("heard"))

    recognizer = QwenAsrRecognizer(
        api_key="test",
        chunker=Base64AudioChunker(chunk_bytes=4),
        transport=httpx.MockTransport(handler),
    )

    assert await recognizer.transcribe(b"abcd") == "heard"
    assert captured == [
        {
            "model": "qwen-audio-3.1-asr-flash",
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": "data:audio/wav;base64,YWJjZA=="},
                            }
                        ],
                    }
                ]
            },
            "parameters": {"format": "wav", "sample_rate": "16000"},
        }
    ]


@pytest.mark.asyncio
async def test_qwen_asr_uses_the_explicit_local_fallback_after_transport_failure() -> None:
    class LocalFallback:
        async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
            assert audio_bytes == b"audio"
            assert mime_type == "audio/wav"
            return "local transcript"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    recognizer = QwenAsrRecognizer(
        api_key="test",
        local_fallback=LocalFallback(),
        transport=httpx.MockTransport(handler),
    )

    assert await recognizer.transcribe(b"audio") == "local transcript"


@pytest.mark.asyncio
async def test_asr_request_goes_to_the_public_dashscope_endpoint_with_the_asr_key() -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=native_reply("heard"))

    recognizer = QwenAsrRecognizer(api_key=_ASR_CREDENTIAL, transport=httpx.MockTransport(handler))

    assert await recognizer.transcribe(b"audio") == "heard"
    (request,) = captured
    assert str(request.url) == _ASR_URL
    assert request.url.host == "dashscope.aliyuncs.com"
    assert request.headers["Authorization"] == f"Bearer {_ASR_CREDENTIAL}"
    assert json.loads(request.content)["model"] == "qwen-audio-3.1-asr-flash"


def test_asr_identity_records_the_real_asr_endpoint() -> None:
    assert QWEN_ASR_IDENTITY.id == "qwen"
    assert QWEN_ASR_IDENTITY.model == "qwen-audio-3.1-asr-flash"
    assert QWEN_ASR_IDENTITY.base_url == DASHSCOPE_ASR_BASE_URL
    assert QWEN_ASR_IDENTITY.base_url == "https://dashscope.aliyuncs.com/api/v1"
    assert QWEN_ASR_IDENTITY.base_url != TOKEN_PLAN_BASE_URL


@pytest.mark.asyncio
async def test_asr_endpoint_cannot_be_chosen_by_the_caller_or_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "VIDSNAP_ASR_BASE_URL",
        "VIDSNAP_QWEN_BASE_URL",
        "QWEN_BASE_URL",
        "DASHSCOPE_BASE_URL",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.setenv(name, "https://example.invalid/v1")
    urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=native_reply("heard"))

    with pytest.raises(TypeError):
        QwenAsrRecognizer(
            api_key=_ASR_CREDENTIAL,
            base_url="https://example.invalid/v1",
        )
    recognizer = QwenAsrRecognizer(api_key=_ASR_CREDENTIAL, transport=httpx.MockTransport(handler))
    await recognizer.transcribe(b"audio")

    assert urls == [_ASR_URL]


@pytest.mark.asyncio
async def test_asr_requests_carry_an_explicit_timeout_not_the_httpx_default() -> None:
    timeouts: list[dict[str, float | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json=native_reply("heard"))

    transport = httpx.MockTransport(handler)
    await QwenAsrRecognizer(api_key=_ASR_CREDENTIAL, transport=transport).transcribe(b"audio")
    await QwenAsrRecognizer(
        api_key=_ASR_CREDENTIAL, timeout_seconds=45.0, transport=transport
    ).transcribe(b"audio")

    every = {"connect": 120.0, "read": 120.0, "write": 120.0, "pool": 120.0}
    assert timeouts == [every, {name: 45.0 for name in every}]
    assert all(value != 5.0 for value in timeouts[0].values())


@pytest.mark.parametrize("timeout_seconds", [0, -1.0])
def test_asr_timeout_must_be_positive(timeout_seconds: float) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        QwenAsrRecognizer(api_key=_ASR_CREDENTIAL, timeout_seconds=timeout_seconds)


@pytest.mark.asyncio
async def test_asr_write_timeout_is_categorized_and_leaks_nothing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.WriteTimeout("sentinel-body-text-0f3e", request=request)

    recognizer = QwenAsrRecognizer(api_key=_ASR_CREDENTIAL, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as excinfo:
        await recognizer.transcribe(b"audio")

    failure = excinfo.value.failure
    assert isinstance(failure, ProviderFailure) and failure.category == "write_timeout"
    serialized = json.dumps(failure.as_payload()) + str(excinfo.value)
    for marker in (_ASR_CREDENTIAL, "dashscope", "https://", "Bearer", "sentinel-body-text-0f3e"):
        assert marker not in serialized


@pytest.mark.asyncio
async def test_asr_without_a_key_is_blocked_before_any_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent without a key")

    recognizer = QwenAsrRecognizer(api_key=None, transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderUnavailable) as excinfo:
        await recognizer.transcribe(b"audio")
    assert "VIDSNAP_ASR_API_KEY" in str(excinfo.value)
