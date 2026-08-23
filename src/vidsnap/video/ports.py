"""Typed boundary for local FFmpeg-backed media inspection."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

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

    async def extract_audio(self, source: Path, output_path: Path) -> Path:
        """Extract local mono WAV audio for an in-memory ASR port."""
