"""In-memory Base64 Qwen-ASR requests with an optional local-plugin fallback."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from vidsnap.config import TOKEN_PLAN_BASE_URL
from vidsnap.providers.base import ProviderError, ProviderUnavailable

QWEN_ASR_MODEL = "qwen3-asr-flash"


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """One in-memory Base64 fragment; it has no object-storage location."""

    index: int
    data_base64: str


class Base64AudioChunker:
    """Split local audio bytes before sending them to the approved ASR model."""

    def __init__(self, *, chunk_bytes: int = 8 * 1024 * 1024) -> None:
        if chunk_bytes < 1:
            raise ValueError("chunk_bytes must be positive")
        self.chunk_bytes = chunk_bytes

    def encode(self, audio_bytes: bytes) -> list[AudioChunk]:
        """Return ordered Base64 chunks without writing audio to cloud storage."""
        return [
            AudioChunk(
                index=index,
                data_base64=base64.b64encode(
                    audio_bytes[offset : offset + self.chunk_bytes]
                ).decode("ascii"),
            )
            for index, offset in enumerate(range(0, len(audio_bytes), self.chunk_bytes))
        ]


class SpeechRecognizer(Protocol):
    """Port for either Qwen ASR or a user-installed local recognizer plugin."""

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        """Return text without persisting audio or transcript to object storage."""


class QwenAsrRecognizer:
    """Use the fixed Qwen ASR model with Base64 data-URI messages."""

    def __init__(
        self,
        *,
        api_key: str | None,
        chunker: Base64AudioChunker | None = None,
        local_fallback: SpeechRecognizer | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
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
            raise ProviderUnavailable("No local Qwen key is configured; ASR is blocked.")
        chunks = self._chunker.encode(audio_bytes)
        if not chunks:
            return ""
        texts: list[str] = []
        async with httpx.AsyncClient(
            base_url=f"{TOKEN_PLAN_BASE_URL}/",
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
                    raise ProviderError("Qwen ASR request failed") from error
                try:
                    content = response.json()["choices"][0]["message"]["content"]
                except (IndexError, KeyError, TypeError) as error:
                    raise ProviderError("provider response did not contain ASR text") from error
                if not isinstance(content, str):
                    raise ProviderError("provider ASR content must be a string")
                texts.append(content)
        return "\n".join(texts)


def audio_chunks_for_request(
    audio_bytes: bytes,
    *,
    chunker: Base64AudioChunker,
) -> Sequence[AudioChunk]:
    """Small seam for inspectable request construction in adapters and tests."""
    return chunker.encode(audio_bytes)
