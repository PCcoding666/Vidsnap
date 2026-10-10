"""Oversized WAV audio is split into standalone WAV files, never raw byte slices.

Every WAV here is synthesized in the test from deterministic bytes; no media
files are read.
"""

from __future__ import annotations

import base64
import io
import json
import struct
import wave
from dataclasses import dataclass

import httpx
import pytest

from vidsnap.providers.asr import AudioChunk, Base64AudioChunker, QwenAsrRecognizer
from vidsnap.providers.base import ProviderError

_CANONICAL_HEADER_BYTES = 44


def _pcm(length: int) -> bytes:
    """Deterministic, non-repeating-looking sample bytes."""
    return bytes((index * 7 + 3) % 251 for index in range(length))


def _fmt_chunk(
    *, tag: int = 1, channels: int = 1, sample_rate: int = 16_000, bits: int = 16
) -> bytes:
    block_align = channels * bits // 8
    return b"fmt " + struct.pack(
        "<IHHIIHH", 16, tag, channels, sample_rate, sample_rate * block_align, block_align, bits
    )


def _info_chunk() -> bytes:
    """An ffmpeg-style INFO list ahead of the audio, with an odd, padded sub-chunk."""
    text = b"Lavf60.3.1\x00"  # 11 bytes, so the sub-chunk needs a pad byte
    sub_chunk = b"ISFT" + struct.pack("<I", len(text)) + text + b"\x00"
    payload = b"INFO" + sub_chunk
    return b"LIST" + struct.pack("<I", len(payload)) + payload


def _wav(
    pcm: bytes,
    *,
    tag: int = 1,
    channels: int = 1,
    sample_rate: int = 16_000,
    bits: int = 16,
    with_info: bool = False,
) -> bytes:
    chunks = [_fmt_chunk(tag=tag, channels=channels, sample_rate=sample_rate, bits=bits)]
    if with_info:
        chunks.append(_info_chunk())
    chunks.append(b"data" + struct.pack("<I", len(pcm)) + pcm + b"\x00" * (len(pcm) & 1))
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


@dataclass(frozen=True)
class _StandaloneWav:
    channels: int
    sample_rate: int
    bits: int
    pcm: bytes


def _parse_standalone_wav(data: bytes) -> _StandaloneWav:
    """Parse one chunk's RIFF header byte by byte; every field must be consistent."""
    assert data[0:4] == b"RIFF"
    assert struct.unpack_from("<I", data, 4)[0] == len(data) - 8
    assert data[8:16] == b"WAVEfmt "
    assert struct.unpack_from("<I", data, 16)[0] == 16
    tag, channels, rate, byte_rate, block_align, bits = struct.unpack_from("<HHIIHH", data, 20)
    assert tag == 1
    assert block_align == channels * bits // 8
    assert byte_rate == rate * block_align
    assert data[36:40] == b"data"
    data_size = struct.unpack_from("<I", data, 40)[0]
    assert data_size % block_align == 0
    assert len(data) == _CANONICAL_HEADER_BYTES + data_size + (data_size & 1)
    # The standard library must also accept it as a readable WAV file.
    with wave.open(io.BytesIO(data), "rb") as reader:
        assert (reader.getnchannels(), reader.getframerate(), reader.getsampwidth() * 8) == (
            channels,
            rate,
            bits,
        )
        assert reader.getnframes() == data_size // block_align
        assert reader.readframes(reader.getnframes()) == data[44 : 44 + data_size]
    return _StandaloneWav(channels, rate, bits, data[44 : 44 + data_size])


def _decoded(chunks: list[AudioChunk]) -> list[bytes]:
    return [base64.b64decode(chunk.data_base64, validate=True) for chunk in chunks]


@pytest.mark.parametrize("with_info", [False, True], ids=["plain-header", "ffmpeg-info-list"])
def test_oversized_wav_is_split_into_standalone_wav_files(with_info: bool) -> None:
    pcm = _pcm(2200)  # 1100 frames of 16 kHz mono 16-bit audio
    wav = _wav(pcm, with_info=with_info)

    chunks = Base64AudioChunker(chunk_bytes=544).encode(wav)

    pieces = _decoded(chunks)
    assert [chunk.index for chunk in chunks] == [0, 1, 2, 3, 4]
    assert all(len(piece) <= 544 for piece in pieces)
    parsed = [_parse_standalone_wav(piece) for piece in pieces]
    assert [len(item.pcm) for item in parsed] == [500, 500, 500, 500, 200]
    assert {(item.channels, item.sample_rate, item.bits) for item in parsed} == {(1, 16_000, 16)}
    assert b"".join(item.pcm for item in parsed) == pcm


@pytest.mark.parametrize("chunk_bytes", [100, 101, 102, 103])
def test_split_never_cuts_through_a_sample_frame(chunk_bytes: int) -> None:
    pcm = _pcm(4 * 50)  # 50 stereo 16-bit frames
    wav = _wav(pcm, channels=2, sample_rate=44_100, with_info=True)

    pieces = _decoded(Base64AudioChunker(chunk_bytes=chunk_bytes).encode(wav))

    parsed = [_parse_standalone_wav(piece) for piece in pieces]
    assert all(len(piece) <= chunk_bytes for piece in pieces)
    assert [len(item.pcm) for item in parsed] == [56, 56, 56, 32]
    assert {(item.channels, item.sample_rate) for item in parsed} == {(2, 44_100)}
    assert b"".join(item.pcm for item in parsed) == pcm


@pytest.mark.parametrize("chunk_bytes", [99, 100])
def test_odd_length_chunks_are_padded_and_still_fit_the_limit(chunk_bytes: int) -> None:
    pcm = _pcm(1001)  # 8-bit mono, so a chunk's audio can have an odd length
    wav = _wav(pcm, bits=8)

    pieces = _decoded(Base64AudioChunker(chunk_bytes=chunk_bytes).encode(wav))

    parsed = [_parse_standalone_wav(piece) for piece in pieces]
    assert all(len(piece) <= chunk_bytes for piece in pieces)
    assert b"".join(item.pcm for item in parsed) == pcm


def test_wav_that_fits_in_one_chunk_is_sent_unchanged() -> None:
    wav = _wav(_pcm(100), with_info=True)

    (chunk,) = Base64AudioChunker(chunk_bytes=len(wav)).encode(wav)

    assert chunk.index == 0
    assert base64.b64decode(chunk.data_base64) == wav


def test_truncated_wav_keeps_only_whole_frames() -> None:
    pcm = _pcm(2200)
    wav = _wav(pcm)[:-1]  # the header still claims 2200 bytes of audio

    pieces = _decoded(Base64AudioChunker(chunk_bytes=544).encode(wav))

    parsed = [_parse_standalone_wav(piece) for piece in pieces]
    assert b"".join(item.pcm for item in parsed) == pcm[:2198]


def test_streamed_wav_with_unknown_data_length_runs_to_the_end() -> None:
    pcm = _pcm(2200)
    wav = bytearray(_wav(pcm))
    wav[40:44] = struct.pack("<I", 0xFFFFFFFF)

    pieces = _decoded(Base64AudioChunker(chunk_bytes=544).encode(bytes(wav)))

    parsed = [_parse_standalone_wav(piece) for piece in pieces]
    assert b"".join(item.pcm for item in parsed) == pcm


def test_default_chunk_size_keeps_the_base64_request_under_ten_megabytes() -> None:
    chunker = Base64AudioChunker()

    assert chunker.chunk_bytes == 7_000_000
    encoded_length = 4 * -(-chunker.chunk_bytes // 3)
    assert encoded_length < 10_000_000  # the provider's documented request limit
    assert chunker.chunk_bytes / 32_000 < 300  # seconds of 16 kHz mono 16-bit, under 5 minutes


def test_default_limit_sends_a_wav_at_the_limit_whole_and_splits_one_byte_more() -> None:
    limit = Base64AudioChunker().chunk_bytes
    fits = _wav(b"\x01\x02" * ((limit - _CANONICAL_HEADER_BYTES) // 2))
    assert len(fits) == limit
    assert len(Base64AudioChunker().encode(fits)) == 1

    too_big = _wav(b"\x01\x02" * ((limit - _CANONICAL_HEADER_BYTES) // 2 + 1))
    pieces = _decoded(Base64AudioChunker().encode(too_big))

    assert len(pieces) == 2
    assert all(len(piece) <= limit for piece in pieces)
    parsed = [_parse_standalone_wav(piece) for piece in pieces]
    assert sum(len(item.pcm) for item in parsed) == len(too_big) - _CANONICAL_HEADER_BYTES


def test_empty_audio_has_no_chunks() -> None:
    assert Base64AudioChunker().encode(b"") == []


def test_non_wav_audio_that_fits_is_sent_whole() -> None:
    audio = b"\xff\xfb" * 10

    (chunk,) = Base64AudioChunker(chunk_bytes=20).encode(audio)

    assert base64.b64decode(chunk.data_base64) == audio


@pytest.mark.parametrize(
    "audio",
    [
        pytest.param(b"\xff\xfb" * 100, id="mp3-like"),
        pytest.param(_wav(_pcm(400), tag=3, bits=32), id="float-wav"),
        pytest.param(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 200, id="no-fmt-or-data"),
        pytest.param(
            b"RIFF\x00\x00\x00\x00WAVE" + b"junk" + b"\xff\xff\xff\xff" * 50, id="bad-size"
        ),
    ],
)
def test_oversized_audio_that_cannot_be_split_is_rejected_not_sliced(audio: bytes) -> None:
    with pytest.raises(ProviderError, match="PCM WAV"):
        Base64AudioChunker(chunk_bytes=64).encode(audio)


@pytest.mark.parametrize("chunk_bytes", [43, 44, 45])
def test_chunk_limit_too_small_for_a_header_and_one_frame_is_rejected(chunk_bytes: int) -> None:
    wav = _wav(_pcm(200))

    with pytest.raises(ProviderError, match="chunk_bytes"):
        Base64AudioChunker(chunk_bytes=chunk_bytes).encode(wav)


@pytest.mark.asyncio
async def test_recognizer_sends_one_standalone_wav_per_request_and_joins_in_order() -> None:
    pcm = _pcm(2200)
    wav = _wav(pcm, with_info=True)
    data_uris: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][0]["content"][0]
        data_uris.append(content["input_audio"])
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"part {len(data_uris)}"}}]}
        )

    recognizer = QwenAsrRecognizer(
        api_key="test",
        chunker=Base64AudioChunker(chunk_bytes=544),
        transport=httpx.MockTransport(handler),
    )

    assert await recognizer.transcribe(wav) == "part 1\npart 2\npart 3\npart 4\npart 5"
    prefix = "data:audio/wav;base64,"
    assert all(uri.startswith(prefix) for uri in data_uris)
    parsed = [
        _parse_standalone_wav(base64.b64decode(uri.removeprefix(prefix))) for uri in data_uris
    ]
    assert b"".join(item.pcm for item in parsed) == pcm


@pytest.mark.asyncio
async def test_recognizer_rejects_unsplittable_audio_before_any_request() -> None:
    class LocalFallback:
        async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
            return "local transcript"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent for audio that cannot be split")

    audio = b"\xff\xfb" * 100
    transport = httpx.MockTransport(handler)
    chunker = Base64AudioChunker(chunk_bytes=64)

    with pytest.raises(ProviderError, match="PCM WAV"):
        await QwenAsrRecognizer(api_key="test", chunker=chunker, transport=transport).transcribe(
            audio
        )
    with_fallback = QwenAsrRecognizer(
        api_key="test", chunker=chunker, local_fallback=LocalFallback(), transport=transport
    )
    assert await with_fallback.transcribe(audio) == "local transcript"
