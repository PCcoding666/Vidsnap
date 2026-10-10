"""Compressed, time-segmented audio for speech recognition.

Pure types and constants. The FFmpeg work that produces these files lives in
``vidsnap.video.probe``; callers reach it only through ``vidsnap.video.ports``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

CompressedAudioFormat = Literal["mp3", "aac"]
AudioFormat = Literal["mp3", "aac", "wav"]

ASR_SAMPLE_RATE_HZ = 16_000
"""Hz of every ASR input; ``qwen3-asr-flash`` resamples to 16 kHz, so more adds only bytes."""

ASR_AUDIO_BITRATE_KBPS = 48
"""Bitrate of compressed ASR input: about 6 KB per second (21.6 MB per hour) of mono speech."""

ASR_SEGMENT_SECONDS = 240.0
"""Longest compressed ASR segment, in seconds.

``qwen3-asr-flash`` accepts at most 5 minutes and 10 MB (after Base64) per request.
240 s keeps 60 s of headroom under the five minutes, because a segment can run past
its target by one codec frame and a window may be rounded up. At 48 kbps a segment is
about 1.4 MB, or 1.9 MB once Base64-encoded, so duration is always the binding limit.
"""

MIN_TAIL_SEGMENT_SECONDS = 1.0
"""A final segment shorter than this is merged into its neighbours instead of sent alone."""

AUDIO_MIME_TYPES: Mapping[AudioFormat, str] = {
    "mp3": "audio/mpeg",
    "aac": "audio/aac",
    "wav": "audio/wav",
}


@dataclass(frozen=True, slots=True)
class AudioSegment:
    """One standalone audio file prepared for a single recognition request.

    ``index`` is the file's order in the extracted range, and ``size_bytes`` its size
    before Base64 encoding.
    """

    path: Path
    index: int
    audio_format: AudioFormat
    size_bytes: int

    @property
    def mime_type(self) -> str:
        """The MIME type to put in the request's data URI."""
        return AUDIO_MIME_TYPES[self.audio_format]


def audio_trace_summary(segments: Sequence[AudioSegment]) -> dict[str, JsonValue]:
    """The audio that was sent to the recognizer, for the run's trace events.

    Uses plain summary keys of the existing ``transcribe_audio`` events; it adds
    no event kind and no schema.
    """
    formats = {segment.audio_format for segment in segments}
    return {
        "audio_format": next(iter(formats)) if len(formats) == 1 else "mixed",
        "audio_segments": len(segments),
        "audio_bytes": sum(segment.size_bytes for segment in segments),
        # A whole-file WAV is not cut by duration; the recognizer cuts it by size.
        "audio_segment_seconds": None if "wav" in formats else ASR_SEGMENT_SECONDS,
    }
