"""In-memory Base64 Qwen-ASR requests with an optional local-plugin fallback."""

from __future__ import annotations

import base64
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from vidsnap.config import DASHSCOPE_ASR_BASE_URL
from vidsnap.providers.base import ProviderError, ProviderIdentity, ProviderUnavailable
from vidsnap.providers.failures import http_failure, invalid_response_failure

QWEN_ASR_MODEL = "qwen3-asr-flash"
QWEN_ASR_IDENTITY = ProviderIdentity(
    id="qwen", model=QWEN_ASR_MODEL, base_url=DASHSCOPE_ASR_BASE_URL
)


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """One in-memory Base64 fragment; it has no object-storage location."""

    index: int
    data_base64: str


# Raw bytes per request. The provider documents a 10 MB limit on the Base64-encoded input
# and 5 minutes of audio; 7_000_000 bytes encode to about 9.3 MB and are about 218 s of
# 16 kHz mono 16-bit audio.
DEFAULT_CHUNK_BYTES = 7_000_000
_WAV_HEADER_BYTES = 44
_PCM_FORMAT_TAG = 1
_UNKNOWN_DATA_SIZE = 0xFFFFFFFF


@dataclass(frozen=True, slots=True)
class _PcmWav:
    """Where the audio of one PCM WAV file sits, and the format it is in."""

    channels: int
    sample_rate: int
    bits_per_sample: int
    block_align: int
    data_start: int
    data_end: int


def _parse_pcm_wav(audio: bytes) -> _PcmWav | None:
    """Locate the PCM audio of a WAV file, or return ``None`` if it is anything else.

    Walks the RIFF chunks instead of assuming a 44-byte header, because encoders
    such as ffmpeg put a metadata list ahead of the audio. A declared audio size
    that is unknown (``0xFFFFFFFF``) or larger than the file is clamped to the
    end of the file.
    """
    if len(audio) < 12 or audio[0:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return None
    fmt: tuple[int, int, int, int] | None = None
    position = 12
    while position + 8 <= len(audio):
        chunk_id = audio[position : position + 4]
        (chunk_size,) = struct.unpack_from("<I", audio, position + 4)
        body = position + 8
        if chunk_id == b"fmt ":
            if chunk_size < 16 or body + 16 > len(audio):
                return None
            tag, channels, sample_rate, _, block_align, bits = struct.unpack_from(
                "<HHIIHH", audio, body
            )
            if (
                tag != _PCM_FORMAT_TAG
                or channels < 1
                or sample_rate < 1
                or bits not in (8, 16, 24, 32)
                or block_align != channels * bits // 8
            ):
                return None
            fmt = (channels, sample_rate, bits, block_align)
        elif chunk_id == b"data":
            if fmt is None:
                return None
            end = (
                len(audio)
                if chunk_size == _UNKNOWN_DATA_SIZE
                else min(body + chunk_size, len(audio))
            )
            return _PcmWav(*fmt, data_start=body, data_end=end)
        position = body + chunk_size + (chunk_size & 1)
    return None


def _split_pcm_wav(audio: bytes, wav: _PcmWav, chunk_bytes: int) -> list[bytes]:
    """Cut PCM audio on frame boundaries into standalone files of at most ``chunk_bytes``."""
    frame = wav.block_align
    max_data = (chunk_bytes - _WAV_HEADER_BYTES) // frame * frame
    # RIFF pads an odd-sized chunk with one byte; keep that byte inside the limit.
    while max_data > 0 and _WAV_HEADER_BYTES + max_data + (max_data & 1) > chunk_bytes:
        max_data -= frame
    if max_data < frame:
        raise ProviderError(
            f"chunk_bytes={chunk_bytes} cannot hold a WAV header and one audio frame"
        )
    pieces: list[bytes] = []
    for offset in range(wav.data_start, wav.data_end, max_data):
        pcm = audio[offset : min(offset + max_data, wav.data_end)]
        pcm = pcm[: len(pcm) - len(pcm) % frame]  # a truncated file may end mid-frame
        if pcm:
            pieces.append(_wav_header(wav, len(pcm)) + pcm + b"\x00" * (len(pcm) & 1))
    return pieces


def _wav_header(wav: _PcmWav, data_length: int) -> bytes:
    """The canonical 44-byte RIFF/WAVE header for ``data_length`` bytes of PCM."""
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_length + (data_length & 1),
        b"WAVE",
        b"fmt ",
        16,
        _PCM_FORMAT_TAG,
        wav.channels,
        wav.sample_rate,
        wav.sample_rate * wav.block_align,
        wav.block_align,
        wav.bits_per_sample,
        b"data",
        data_length,
    )


class Base64AudioChunker:
    """Split local audio bytes before sending them to the approved ASR model.

    Every chunk must be a file the provider can decode on its own. Audio that fits
    in ``chunk_bytes`` is sent whole and unchanged. A larger PCM WAV file is cut on
    sample-frame boundaries and each piece gets its own header with the input's
    sample rate, channel count and bit depth. Larger audio in any other format
    cannot be cut without a decoder, so it raises ``ProviderError``.
    """

    def __init__(self, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> None:
        if chunk_bytes < 1:
            raise ValueError("chunk_bytes must be positive")
        self.chunk_bytes = chunk_bytes

    def encode(self, audio_bytes: bytes) -> list[AudioChunk]:
        """Return ordered Base64 chunks without writing audio to cloud storage."""
        if not audio_bytes:
            return []
        if len(audio_bytes) <= self.chunk_bytes:
            pieces = [audio_bytes]
        else:
            wav = _parse_pcm_wav(audio_bytes)
            if wav is None:
                raise ProviderError(
                    f"audio is {len(audio_bytes)} bytes, over the {self.chunk_bytes}-byte "
                    "request limit, and only PCM WAV audio can be split into valid chunks"
                )
            pieces = _split_pcm_wav(audio_bytes, wav, self.chunk_bytes)
        return [
            AudioChunk(index=index, data_base64=base64.b64encode(piece).decode("ascii"))
            for index, piece in enumerate(pieces)
        ]


class SpeechRecognizer(Protocol):
    """Port for either Qwen ASR or a user-installed local recognizer plugin."""

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        """Return text without persisting audio or transcript to object storage."""


class QwenAsrRecognizer:
    """Use the fixed Qwen ASR model with Base64 data-URI messages.

    Requests go to the fixed public DashScope endpoint, never to Token Plan, which
    serves text models only. The endpoint is not a parameter.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        chunker: Base64AudioChunker | None = None,
        local_fallback: SpeechRecognizer | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._chunker = chunker or Base64AudioChunker()
        self._local_fallback = local_fallback
        self._transport = transport

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        """Try Qwen ASR first, then an explicitly supplied local plugin if needed."""
        try:
            return await self._transcribe_with_qwen(audio_bytes, mime_type=mime_type)
        except ProviderError:
            if self._local_fallback is None:
                raise
            return await self._local_fallback.transcribe(audio_bytes, mime_type=mime_type)

    async def _transcribe_with_qwen(self, audio_bytes: bytes, *, mime_type: str) -> str:
        if not self._api_key:
            raise ProviderUnavailable(
                "No local ASR key is configured (VIDSNAP_ASR_API_KEY, else "
                "VIDSNAP_QWEN_API_KEY or QWEN_API_KEY); ASR is blocked."
            )
        chunks = self._chunker.encode(audio_bytes)
        if not chunks:
            return ""
        texts: list[str] = []
        async with httpx.AsyncClient(
            base_url=f"{DASHSCOPE_ASR_BASE_URL}/",
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            for chunk in chunks:
                payload = {
                    "model": QWEN_ASR_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": (f"data:{mime_type};base64,{chunk.data_base64}"),
                                }
                            ],
                        }
                    ],
                }
                try:
                    response = await client.post(
                        "chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise ProviderError(
                        "Qwen ASR request failed", failure=http_failure(error, input_bytes=None)
                    ) from error
                try:
                    content = response.json()["choices"][0]["message"]["content"]
                except (IndexError, KeyError, TypeError) as error:
                    raise ProviderError(
                        "provider response did not contain ASR text",
                        failure=invalid_response_failure(None, input_bytes=None),
                    ) from error
                if not isinstance(content, str):
                    raise ProviderError(
                        "provider ASR content must be a string",
                        failure=invalid_response_failure(None, input_bytes=None),
                    )
                texts.append(content)
        return "\n".join(texts)


def audio_chunks_for_request(
    audio_bytes: bytes,
    *,
    chunker: Base64AudioChunker,
) -> Sequence[AudioChunk]:
    """Small seam for inspectable request construction in adapters and tests."""
    return chunker.encode(audio_bytes)
