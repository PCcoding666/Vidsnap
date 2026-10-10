"""Typed boundary for local FFmpeg-backed media inspection."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from vidsnap.video.audio import (
    ASR_SEGMENT_SECONDS,
    AudioSegment,
    CompressedAudioFormat,
)
from vidsnap.video.probe import ExtractedFrame, MediaProbe
from vidsnap.video.sampling import FrameCandidate


class FFmpegPort(Protocol):
    """Local media operations required by the harness reconnaissance skills."""

    async def probe(self, source: Path) -> MediaProbe:
        """Return deterministic stream metadata for a local source."""

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        """Return scene, motion, and coverage candidates without a model call."""

    async def extract_frames(
        self,
        source: Path,
        candidates: Sequence[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        """Extract only selected local evidence frames."""

    async def extract_timeline_frames(
        self,
        source: Path,
        *,
        fps: int,
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        """Extract a complete fixed-rate timeline in one local operation."""

    async def extract_audio(
        self,
        source: Path,
        output_path: Path,
        *,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Path:
        """Extract local mono WAV audio, optionally bounded by a time window."""

    async def extract_audio_segments(
        self,
        source: Path,
        output_dir: Path,
        *,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
        segment_seconds: float = ASR_SEGMENT_SECONDS,
        audio_format: CompressedAudioFormat = "mp3",
    ) -> list[AudioSegment]:
        """Extract compressed 16 kHz mono audio as ordered, standalone files.

        Segments are cut by duration, each at most about ``segment_seconds`` long,
        so a file can be sent to a recognizer on its own.
        """


async def extract_asr_audio(
    media: FFmpegPort,
    source: Path,
    segments_dir: Path,
    legacy_wav_path: Path,
    *,
    compressed: bool,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> list[AudioSegment]:
    """Prepare the audio one recognizer will be sent, through the media port.

    A recognizer that accepts compressed audio (``accepts_compressed_audio``) gets
    MP3 segments of at most ``ASR_SEGMENT_SECONDS`` each. Every other recognizer, and
    any port written before segmenting existed, keeps the single mono WAV file at
    ``legacy_wav_path``, which the recognizer cuts by size if it must.
    """
    segmenter = getattr(media, "extract_audio_segments", None)
    if compressed and segmenter is not None:
        segments: list[AudioSegment] = await segmenter(
            source,
            segments_dir,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        return segments
    path = await media.extract_audio(
        source, legacy_wav_path, start_seconds=start_seconds, end_seconds=end_seconds
    )
    return [AudioSegment(path=path, index=0, audio_format="wav", size_bytes=path.stat().st_size)]
