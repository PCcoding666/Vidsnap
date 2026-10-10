"""Compressed audio is sent whole with its real MIME type, never cut by bytes.

All audio here is a synthetic byte string; no media is read.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from vidsnap.providers.asr import (
    MAX_REQUEST_BASE64_BYTES,
    Base64AudioChunker,
    QwenAsrRecognizer,
)
from vidsnap.providers.base import ProviderError


def _recorder(texts: list[str] | None = None):
    requests: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        reply = (texts or ["heard"])[min(len(requests), len(texts or ["heard"])) - 1]
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    return requests, httpx.MockTransport(handler)


def _data_uri(request: dict[str, object]) -> str:
    messages = request["messages"]
    assert isinstance(messages, list)
    return str(messages[0]["content"][0]["input_audio"])


@pytest.mark.asyncio
@pytest.mark.parametrize("mime_type", ["audio/mpeg", "audio/aac"])
async def test_the_real_mime_type_goes_into_the_data_uri(mime_type: str) -> None:
    requests, transport = _recorder()
    audio = b"ID3\x04\x00" + bytes(range(256)) * 4

    recognizer = QwenAsrRecognizer(api_key="test", transport=transport)

    assert await recognizer.transcribe(audio, mime_type=mime_type) == "heard"
    (request,) = requests
    assert _data_uri(request) == f"data:{mime_type};base64,{base64.b64encode(audio).decode()}"


@pytest.mark.asyncio
async def test_wav_is_still_the_default_mime_type() -> None:
    requests, transport = _recorder()

    await QwenAsrRecognizer(api_key="test", transport=transport).transcribe(b"abcd")

    assert _data_uri(requests[0]).startswith("data:audio/wav;base64,")


@pytest.mark.asyncio
async def test_compressed_audio_is_never_cut_by_bytes() -> None:
    requests, transport = _recorder()
    audio = b"\xff\xfb" * 500  # far over the 64-byte limit that would cut a WAV
    recognizer = QwenAsrRecognizer(
        api_key="test", chunker=Base64AudioChunker(chunk_bytes=64), transport=transport
    )

    assert await recognizer.transcribe(audio, mime_type="audio/mpeg") == "heard"
    assert len(requests) == 1
    assert _data_uri(requests[0]).split(",", 1)[1] == base64.b64encode(audio).decode()


@pytest.mark.asyncio
async def test_wav_over_the_limit_is_still_cut_into_standalone_files() -> None:
    requests, transport = _recorder(["a", "b"])
    pcm = bytes(1000)
    header = (
        b"RIFF"
        + (36 + len(pcm)).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16_000).to_bytes(4, "little")
        + (32_000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(pcm).to_bytes(4, "little")
    )
    recognizer = QwenAsrRecognizer(
        api_key="test", chunker=Base64AudioChunker(chunk_bytes=600), transport=transport
    )

    assert await recognizer.transcribe(header + pcm) == "a\nb"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_compressed_audio_over_the_base64_limit_fails_before_any_request() -> None:
    requests, transport = _recorder()
    over = MAX_REQUEST_BASE64_BYTES * 3 // 4 + 3
    recognizer = QwenAsrRecognizer(api_key="test", transport=transport)

    with pytest.raises(ProviderError, match="10 MB"):
        await recognizer.transcribe(bytes(over), mime_type="audio/mpeg")
    assert requests == []


def test_chunker_treats_wav_mime_variants_as_wav_and_everything_else_as_whole_files() -> None:
    chunker = Base64AudioChunker(chunk_bytes=8)
    audio = b"x" * 100

    assert len(chunker.encode(audio, mime_type="audio/mpeg")) == 1
    assert len(chunker.encode(audio, mime_type="AUDIO/MPEG; charset=binary")) == 1
    for wav in ("audio/wav", "audio/x-wav", "audio/wave", "audio/WAV"):
        with pytest.raises(ProviderError, match="PCM WAV"):  # 100 bytes of junk over the limit
            chunker.encode(audio, mime_type=wav)


def test_the_recognizer_accepts_compressed_audio_unless_its_fallback_needs_wav() -> None:
    class NeedsWav:
        async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
            return ""

    class TakesAnything(NeedsWav):
        accepts_compressed_audio = True

    assert QwenAsrRecognizer(api_key="test").accepts_compressed_audio is True
    assert (
        QwenAsrRecognizer(api_key="t", local_fallback=NeedsWav()).accepts_compressed_audio is False
    )
    assert (
        QwenAsrRecognizer(api_key="t", local_fallback=TakesAnything()).accepts_compressed_audio
        is True
    )
