"""In-memory Base64 Qwen-Audio ASR requests with an optional local-plugin fallback."""

from __future__ import annotations

import base64
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from vidsnap.config import DASHSCOPE_ASR_BASE_URL
from vidsnap.contracts.failures import ProviderFailure
from vidsnap.providers.base import ProviderError, ProviderIdentity, ProviderUnavailable
from vidsnap.providers.failures import http_failure, invalid_response_failure

QWEN_ASR_MODEL = "qwen-audio-3.1-asr-flash"
QWEN_ASR_IDENTITY = ProviderIdentity(
    id="qwen", model=QWEN_ASR_MODEL, base_url=DASHSCOPE_ASR_BASE_URL
)
# The native DashScope path, relative to `DASHSCOPE_ASR_BASE_URL`. The model is not served by
# the OpenAI-compatible `chat/completions` path.
QWEN_ASR_PATH = "services/aigc/multimodal-generation/generation"
# Every ASR input the harness produces is 16 kHz mono. A WAV file declares its own rate.
_DEFAULT_SAMPLE_RATE = "16000"


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """One in-memory Base64 fragment; it has no object-storage location."""

    index: int
    data_base64: str


# Raw bytes per request. The provider documents a 10 MB limit on the Base64-encoded input
# and 5 minutes of audio; 7_000_000 bytes encode to about 9.3 MB and are about 218 s of
# 16 kHz mono 16-bit audio.
DEFAULT_CHUNK_BYTES = 7_000_000
# The provider's documented limit on one request's Base64-encoded audio.
MAX_REQUEST_BASE64_BYTES = 10_000_000
_WAV_MIME_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"})
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

    Audio that is not WAV by its ``mime_type`` (MP3, AAC) is already one standalone
    file cut by duration upstream. It is never cut by bytes: it is sent whole, or
    refused if its Base64 form would exceed the provider's request limit.
    """

    def __init__(self, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> None:
        if chunk_bytes < 1:
            raise ValueError("chunk_bytes must be positive")
        self.chunk_bytes = chunk_bytes

    def encode(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> list[AudioChunk]:
        """Return ordered Base64 chunks without writing audio to cloud storage."""
        if not audio_bytes:
            return []
        if mime_type.split(";", 1)[0].strip().lower() not in _WAV_MIME_TYPES:
            if 4 * ((len(audio_bytes) + 2) // 3) > MAX_REQUEST_BASE64_BYTES:
                raise ProviderError(
                    f"{mime_type} audio is {len(audio_bytes)} bytes, over the 10 MB Base64 "
                    "request limit; cut it into shorter segments by duration"
                )
            pieces = [audio_bytes]
        elif len(audio_bytes) <= self.chunk_bytes:
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
    """Port for either Qwen ASR or a user-installed local recognizer plugin.

    A recognizer that can decode MP3 and AAC may set ``accepts_compressed_audio = True``.
    The harness then sends compressed segments cut by duration with their real
    ``mime_type``; without it, it sends one mono WAV file with ``audio/wav``.
    """

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        """Return text without persisting audio or transcript to object storage."""


_FORMAT_MIME_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "aac": "audio/aac"}
_COMPRESSED_MIME_FORMATS = {"audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/aac": "aac"}


def _audio_format(mime_type: str) -> str:
    """The ``parameters.format`` for a MIME type; the API requires it to match the bytes."""
    normalized = mime_type.split(";", 1)[0].strip().lower()
    if normalized in _WAV_MIME_TYPES:
        return "wav"
    audio_format = _COMPRESSED_MIME_FORMATS.get(normalized)
    if audio_format is None:
        raise ProviderError(
            f"unsupported audio MIME type {mime_type!r} for ASR; send WAV, MP3 or AAC",
            failure=ProviderFailure(category="validation"),
        )
    return audio_format


def _sample_rate(audio_bytes: bytes, audio_format: str) -> str:
    """The sample rate in Hz as a string: the WAV header's own, else the harness's 16 kHz."""
    if audio_format == "wav":
        wav = _parse_pcm_wav(audio_bytes)
        if wav is not None:
            return str(wav.sample_rate)
    return _DEFAULT_SAMPLE_RATE


def _counter(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _total(values: Sequence[int | None]) -> int | None:
    """The sum, or ``None`` when any request did not report the counter (unknown is not zero)."""
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


@dataclass(frozen=True, slots=True)
class AsrTranscript:
    """The joined text of one recognition plus the usage the provider reported.

    ``audio_seconds`` is the audio duration the provider processed, ``input_tokens`` and
    ``output_tokens`` its billing counters. Each is ``None`` unless every request reported it.
    """

    text: str
    requests: int = 0
    audio_seconds: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def usage_reported(self) -> bool:
        """Whether the provider reported both token counters for every request."""
        return self.input_tokens is not None and self.output_tokens is not None


@dataclass(frozen=True, slots=True)
class _Reply:
    text: str
    audio_seconds: int | None
    input_tokens: int | None
    output_tokens: int | None


def _invalid_response(message: str) -> ProviderError:
    return ProviderError(message, failure=invalid_response_failure(None, input_bytes=None))


def _parse_reply(response: httpx.Response) -> _Reply:
    """Read ``output.text`` (else ``output.sentence.text``) and the ``usage`` counters.

    A reply without text is invalid. The same payload is also repeated under
    ``output.output``; it is not needed.
    """
    try:
        body: Any = response.json()
    except (ValueError, RecursionError) as error:
        raise _invalid_response("provider ASR reply was not JSON") from error
    output = body.get("output") if isinstance(body, dict) else None
    if not isinstance(output, dict):
        raise _invalid_response("provider response did not contain ASR text")
    text = output.get("text")
    if not isinstance(text, str):
        sentence = output.get("sentence")
        text = sentence.get("text") if isinstance(sentence, dict) else None
    if not isinstance(text, str):
        raise _invalid_response("provider response did not contain ASR text")
    usage = body.get("usage")
    if not isinstance(usage, dict):
        usage = output.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    return _Reply(
        text=text,
        audio_seconds=_counter(usage.get("duration")),
        input_tokens=_counter(usage.get("input_tokens")),
        output_tokens=_counter(usage.get("output_tokens")),
    )


class QwenAudioAsrClient:
    """The fixed ASR model on the fixed native DashScope endpoint, one request per chunk.

    Shared by the harness recognizer and the evaluation recognizer, so both send exactly
    the same request. The model and the endpoint are constants, not parameters. Each request
    carries ``parameters.format`` for the real audio (``wav``, ``mp3`` or ``aac``), the
    sample rate, and no ``language_hints``: the model detects the language itself, which
    suits Chinese and English material alike.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        chunker: Base64AudioChunker | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 120.0,
        unavailable_message: str = "No ASR key is configured; ASR is blocked.",
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._chunker = chunker or Base64AudioChunker()
        self._transport = transport
        self._unavailable_message = unavailable_message

    async def recognize(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> AsrTranscript:
        """Send each chunk of the audio and return the joined text and the summed usage."""
        if not self._api_key:
            raise ProviderUnavailable(self._unavailable_message)
        chunks = self._chunker.encode(audio_bytes, mime_type=mime_type)
        if not chunks:
            return AsrTranscript(text="", requests=0)
        audio_format = _audio_format(mime_type)
        sample_rate = _sample_rate(audio_bytes, audio_format)
        data_uri_prefix = f"data:{_FORMAT_MIME_TYPES[audio_format]};base64,"
        replies: list[_Reply] = []
        async with httpx.AsyncClient(
            base_url=f"{DASHSCOPE_ASR_BASE_URL}/",
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            for chunk in chunks:
                payload = {
                    "model": QWEN_ASR_MODEL,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_audio",
                                        "input_audio": {
                                            "data": f"{data_uri_prefix}{chunk.data_base64}"
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                    "parameters": {"format": audio_format, "sample_rate": sample_rate},
                }
                try:
                    response = await client.post(
                        QWEN_ASR_PATH,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise ProviderError(
                        "Qwen ASR request failed", failure=http_failure(error, input_bytes=None)
                    ) from error
                replies.append(_parse_reply(response))
        return AsrTranscript(
            text="\n".join(reply.text for reply in replies),
            requests=len(replies),
            audio_seconds=_total([reply.audio_seconds for reply in replies]),
            input_tokens=_total([reply.input_tokens for reply in replies]),
            output_tokens=_total([reply.output_tokens for reply in replies]),
        )


class QwenAsrRecognizer:
    """Use the fixed Qwen-Audio ASR model with Base64 data-URI messages.

    Requests go to the fixed public DashScope native endpoint, never to Token Plan, which
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
        self._client = QwenAudioAsrClient(
            api_key=api_key,
            chunker=chunker,
            transport=transport,
            timeout_seconds=timeout_seconds,
            unavailable_message=(
                "No local ASR key is configured (VIDSNAP_ASR_API_KEY, else "
                "VIDSNAP_QWEN_API_KEY or QWEN_API_KEY); ASR is blocked."
            ),
        )
        self._local_fallback = local_fallback

    @property
    def accepts_compressed_audio(self) -> bool:
        """Whether callers may send MP3/AAC segments instead of one WAV file.

        The provider decodes them. An explicit ``local_fallback`` receives the same
        bytes and MIME type, so it must declare its own ``accepts_compressed_audio``
        for compressed audio to be used.
        """
        return self._local_fallback is None or bool(
            getattr(self._local_fallback, "accepts_compressed_audio", False)
        )

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        """Try Qwen ASR first, then an explicitly supplied local plugin if needed."""
        try:
            return (await self._client.recognize(audio_bytes, mime_type=mime_type)).text
        except ProviderError:
            if self._local_fallback is None:
                raise
            return await self._local_fallback.transcribe(audio_bytes, mime_type=mime_type)


def audio_chunks_for_request(
    audio_bytes: bytes,
    *,
    chunker: Base64AudioChunker,
) -> Sequence[AudioChunk]:
    """Small seam for inspectable request construction in adapters and tests."""
    return chunker.encode(audio_bytes)
