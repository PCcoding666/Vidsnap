"""Compressed, time-segmented ASR audio behind the media port.

The offline tests use a fake port. The FFmpeg tests synthesise a tone in the test
and skip when FFmpeg is not installed, like the other media-port tests.
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from tests.fixtures.make_synthetic_video import make_synthetic_video
from vidsnap.video.audio import (
    ASR_AUDIO_BITRATE_KBPS,
    ASR_SEGMENT_SECONDS,
    AudioSegment,
    audio_trace_summary,
)
from vidsnap.video.ports import extract_asr_audio
from vidsnap.video.probe import FFmpegError, FFmpegMediaPort, audio_segment_command, choose_format

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg and ffprobe are required for the local integration test",
)


def write_tone(path: Path, seconds: float, *, sample_rate: int = 16_000) -> None:
    """A deterministic 440 Hz mono 16-bit tone, generated here and never committed."""
    frames = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate)))
        for index in range(int(seconds * sample_rate))
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)


def stream_info(path: Path) -> dict[str, str]:
    output = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bit_rate:format=duration",
            "-of",
            "default=noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def decoded_seconds(path: Path) -> float:
    """Decode the whole file; any decoder error fails the test."""
    completed = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ar", "16000", "-ac", "1", "-"],
        capture_output=True,
        check=True,
    )
    assert completed.stderr == b""
    return len(completed.stdout) / 2 / 16_000


def test_segment_length_respects_the_documented_provider_limits() -> None:
    # qwen3-asr-flash: at most 5 minutes and 10 MB after Base64 per request.
    assert ASR_SEGMENT_SECONDS <= 300 - 30
    base64_bytes = 4 * math.ceil(ASR_SEGMENT_SECONDS * ASR_AUDIO_BITRATE_KBPS * 1000 / 8 / 3)
    assert base64_bytes < 10_000_000 / 2  # duration, not size, is the binding limit


def test_segment_command_compresses_to_mono_16khz_mp3_and_cuts_by_time() -> None:
    command = audio_segment_command(
        Path("in.mp4"),
        Path("out"),
        start_seconds=0.0,
        end_seconds=None,
        segment_seconds=240.0,
        audio_format="mp3",
    )

    assert command[0] == "ffmpeg"
    joined = " ".join(command)
    for expected in (
        "-vn",
        "-ac 1",
        "-ar 16000",
        "-c:a libmp3lame",
        "-b:a 48k",
        "-map_metadata -1",
        "-f segment",
        "-segment_time 240",
        "-segment_format mp3",
        "-reset_timestamps 1",
        "-segment_list pipe:1",
    ):
        assert expected in joined
    assert command[-1] == str(Path("out") / "segment-%03d.mp3")
    assert "-ss" not in command and "-to" not in command


def test_segment_command_bounds_a_window_and_selects_aac() -> None:
    command = audio_segment_command(
        Path("in.mp4"),
        Path("out"),
        start_seconds=2.5,
        end_seconds=9.0,
        segment_seconds=60.0,
        audio_format="aac",
    )

    joined = " ".join(command)
    assert "-ss 2.500000" in joined and "-to 9.000000" in joined
    assert "-c:a aac" in joined and "-segment_format adts" in joined
    assert command[-1] == str(Path("out") / "segment-%03d.aac")


def test_mp3_falls_back_to_aac_only_without_the_lame_encoder() -> None:
    with_lame = " A....D libmp3lame           libmp3lame MP3 (MPEG audio layer 3)\n A....D aac AAC"
    without_lame = " A....D aac                  AAC (Advanced Audio Coding)\n"

    assert choose_format("mp3", with_lame) == "mp3"
    assert choose_format("mp3", without_lame) == "aac"
    assert choose_format("aac", with_lame) == "aac"


class _SegmentPort:
    """A fake port that can segment and can also write one WAV."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def extract_audio(
        self, source: Path, output_path: Path, *, start_seconds: float = 0.0, end_seconds=None
    ) -> Path:
        self.calls.append("wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav-bytes")
        return output_path

    async def extract_audio_segments(
        self,
        source: Path,
        output_dir: Path,
        *,
        start_seconds: float = 0.0,
        end_seconds=None,
        segment_seconds: float = ASR_SEGMENT_SECONDS,
        audio_format="mp3",
    ) -> list[AudioSegment]:
        self.calls.append("segments")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "segment-000.mp3"
        path.write_bytes(b"mp3-bytes")
        return [AudioSegment(path, 0, "mp3", 9)]


class _WavOnlyPort:
    async def extract_audio(
        self, source: Path, output_path: Path, *, start_seconds: float = 0.0, end_seconds=None
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav-bytes")
        return output_path


@pytest.mark.asyncio
async def test_compressed_audio_is_requested_only_when_the_recognizer_accepts_it(tmp_path) -> None:
    port = _SegmentPort()
    source = tmp_path / "v.mp4"

    compressed = await extract_asr_audio(
        port, source, tmp_path / "audio", tmp_path / "audio.wav", compressed=True
    )
    legacy = await extract_asr_audio(
        port, source, tmp_path / "audio2", tmp_path / "audio2.wav", compressed=False
    )

    assert [(item.audio_format, item.mime_type) for item in compressed] == [("mp3", "audio/mpeg")]
    assert [(item.audio_format, item.mime_type) for item in legacy] == [("wav", "audio/wav")]
    assert legacy[0].path == tmp_path / "audio2.wav" and legacy[0].size_bytes == 9
    assert port.calls == ["segments", "wav"]


@pytest.mark.asyncio
async def test_a_port_without_segmenting_keeps_the_wav_path(tmp_path) -> None:
    segments = await extract_asr_audio(
        _WavOnlyPort(),
        tmp_path / "v.mp4",
        tmp_path / "audio",
        tmp_path / "audio.wav",
        compressed=True,
    )

    assert [item.audio_format for item in segments] == ["wav"]
    assert segments[0].path.read_bytes() == b"wav-bytes"


def test_trace_summary_marks_a_whole_file_wav_as_not_cut_by_duration(tmp_path) -> None:
    summary = audio_trace_summary([AudioSegment(tmp_path / "a.wav", 0, "wav", 288_044)])

    assert summary["audio_format"] == "wav"
    assert summary["audio_segment_seconds"] is None


def test_trace_summary_records_format_count_and_bytes_sent(tmp_path) -> None:
    segments = [
        AudioSegment(tmp_path / "a.mp3", 0, "mp3", 1_440_000),
        AudioSegment(tmp_path / "b.mp3", 1, "mp3", 360_000),
    ]

    assert audio_trace_summary(segments) == {
        "audio_format": "mp3",
        "audio_segments": 2,
        "audio_bytes": 1_800_000,
        "audio_segment_seconds": ASR_SEGMENT_SECONDS,
    }


@needs_ffmpeg
@pytest.mark.asyncio
async def test_ffmpeg_cuts_a_tone_into_standalone_mp3_files_by_duration(tmp_path) -> None:
    source = tmp_path / "tone.wav"
    write_tone(source, 10.0)

    segments = await FFmpegMediaPort().extract_audio_segments(
        source, tmp_path / "audio", segment_seconds=4.0
    )

    assert [item.index for item in segments] == [0, 1, 2]
    assert [item.path.name for item in segments] == [f"segment-{n:03d}.mp3" for n in range(3)]
    assert all(item.audio_format == "mp3" and item.mime_type == "audio/mpeg" for item in segments)
    total = 0.0
    for item in segments:
        info = stream_info(item.path)
        assert info["codec_name"] == "mp3"
        assert info["sample_rate"] == "16000" and info["channels"] == "1"
        assert int(info["bit_rate"]) == ASR_AUDIO_BITRATE_KBPS * 1000
        assert item.size_bytes == item.path.stat().st_size > 0
        total += decoded_seconds(item.path)  # every segment decodes on its own
    # Each cut costs the decoder about 33 ms; nothing else is lost.
    assert total == pytest.approx(10.0, abs=0.5)
    wav_bytes = 10 * 16_000 * 2
    assert sum(item.size_bytes for item in segments) < wav_bytes / 4


@needs_ffmpeg
@pytest.mark.asyncio
async def test_ffmpeg_segments_only_the_requested_window(tmp_path) -> None:
    source = tmp_path / "tone.wav"
    write_tone(source, 10.0)

    segments = await FFmpegMediaPort().extract_audio_segments(
        source, tmp_path / "audio", start_seconds=2.0, end_seconds=8.0, segment_seconds=4.0
    )

    assert len(segments) == 2
    assert sum(decoded_seconds(item.path) for item in segments) == pytest.approx(6.0, abs=0.4)


@needs_ffmpeg
@pytest.mark.asyncio
async def test_ffmpeg_absorbs_a_sub_second_tail_into_the_previous_segment(tmp_path) -> None:
    source = tmp_path / "tone.wav"
    write_tone(source, 8.3)  # 4 s + 4 s + a 0.3 s runt that a recogniser would reject

    segments = await FFmpegMediaPort().extract_audio_segments(
        source, tmp_path / "audio", segment_seconds=4.0
    )

    assert len(segments) == 2
    assert not (tmp_path / "audio" / "segment-002.mp3").exists()
    assert all(decoded_seconds(item.path) > 3.5 for item in segments)


@needs_ffmpeg
@pytest.mark.asyncio
async def test_ffmpeg_can_write_aac_segments_when_requested(tmp_path) -> None:
    source = tmp_path / "tone.wav"
    write_tone(source, 6.0)

    segments = await FFmpegMediaPort().extract_audio_segments(
        source, tmp_path / "audio", segment_seconds=4.0, audio_format="aac"
    )

    assert [item.path.suffix for item in segments] == [".aac", ".aac"]
    assert all(item.mime_type == "audio/aac" and item.audio_format == "aac" for item in segments)
    for item in segments:
        assert stream_info(item.path)["codec_name"] == "aac"
        assert decoded_seconds(item.path) > 1.5


@needs_ffmpeg
@pytest.mark.asyncio
async def test_ffmpeg_refuses_a_source_without_audio(tmp_path) -> None:
    source = tmp_path / "silent.mp4"
    make_synthetic_video(source)

    with pytest.raises(FFmpegError):
        await FFmpegMediaPort().extract_audio_segments(source, tmp_path / "audio")


@needs_ffmpeg
@pytest.mark.asyncio
async def test_ffmpeg_rejects_invalid_segment_arguments(tmp_path) -> None:
    media = FFmpegMediaPort()
    source = tmp_path / "tone.wav"
    write_tone(source, 1.0)

    with pytest.raises(ValueError, match="segment_seconds"):
        await media.extract_audio_segments(source, tmp_path / "a", segment_seconds=0)
    with pytest.raises(ValueError, match="end_seconds"):
        await media.extract_audio_segments(source, tmp_path / "b", start_seconds=2, end_seconds=1)
    with pytest.raises(ValueError, match="audio_format"):
        await media.extract_audio_segments(source, tmp_path / "c", audio_format="wav")  # type: ignore[arg-type]


@needs_ffmpeg
@pytest.mark.asyncio
async def test_each_real_segment_is_one_valid_standalone_request_in_order(tmp_path) -> None:
    import base64
    import json

    import httpx

    from vidsnap.providers.asr import QwenAsrRecognizer

    source = tmp_path / "tone.wav"
    write_tone(source, 10.0)
    segments = await extract_asr_audio(
        FFmpegMediaPort(),
        source,
        tmp_path / "audio",
        tmp_path / "audio.wav",
        compressed=True,
        end_seconds=10.0,
    )
    uploads: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        uri = json.loads(request.content)["messages"][0]["content"][0]["input_audio"]
        prefix = "data:audio/mpeg;base64,"
        assert uri.startswith(prefix)
        uploads.append(base64.b64decode(uri.removeprefix(prefix)))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"part {len(uploads)}"}}]}
        )

    recognizer = QwenAsrRecognizer(api_key="test", transport=httpx.MockTransport(handler))
    texts = [
        await recognizer.transcribe(item.path.read_bytes(), mime_type=item.mime_type)
        for item in segments
    ]

    assert texts == [f"part {n}" for n in range(1, len(segments) + 1)]
    assert uploads == [item.path.read_bytes() for item in segments]
    assert len(uploads) == 1  # 10 s is far under the 240 s segment length
    assert sum(len(upload) for upload in uploads) < 10 * 16_000 * 2 / 4
