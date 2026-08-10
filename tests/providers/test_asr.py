"""Local-only ASR request construction."""

import base64
import json

import httpx
import pytest

from vidsnap.providers.asr import Base64AudioChunker, QwenAsrRecognizer


def test_asr_chunker_keeps_audio_in_memory_and_base64_encodes_chunks() -> None:
    chunks = Base64AudioChunker(chunk_bytes=4).encode(b"abcdefgh")

    assert [chunk.index for chunk in chunks] == [0, 1]
    assert [chunk.data_base64 for chunk in chunks] == [
        base64.b64encode(b"abcd").decode("ascii"),
        base64.b64encode(b"efgh").decode("ascii"),
    ]


@pytest.mark.asyncio
async def test_qwen_asr_uses_an_in_memory_base64_data_uri() -> None:
    captured: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "heard"}}]})

    recognizer = QwenAsrRecognizer(
        api_key="test",
        chunker=Base64AudioChunker(chunk_bytes=4),
        transport=httpx.MockTransport(handler),
    )

    assert await recognizer.transcribe(b"abcd") == "heard"
    assert captured == [
        {
            "model": "qwen3-asr-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": "data:audio/wav;base64,YWJjZA==",
                        }
                    ],
                }
            ],
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
