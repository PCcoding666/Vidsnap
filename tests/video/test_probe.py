"""FFmpeg media-port integration behavior using generated local media."""

from __future__ import annotations

import shutil

import pytest

from tests.fixtures.make_synthetic_video import make_synthetic_video
from vidsnap.video.probe import FFmpegMediaPort, motion_windows
from vidsnap.video.sampling import FrameCandidate

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg and ffprobe are required for the local integration test",
)


@pytest.mark.asyncio
async def test_ffmpeg_port_probes_and_extracts_adaptive_evidence(tmp_path) -> None:
    source = tmp_path / "synthetic.mp4"
    make_synthetic_video(source)
    media = FFmpegMediaPort()

    probe = await media.probe(source)
    candidates = await media.visual_candidates(source, probe)
    selected = media.sampler.select(candidates, max_frames=2)
    extracted = await media.extract_frames(source, selected, tmp_path / "frames")

    assert 1.9 <= probe.duration_seconds <= 2.1
    assert (probe.width, probe.height) == (64, 64)
    assert len(selected) <= 2 < int(probe.duration_seconds * 2) + 1
    assert all(frame.path.exists() for frame in extracted)
    assert all(0 <= frame.timestamp <= probe.duration_seconds for frame in extracted)


def test_high_motion_windows_are_local_and_merged() -> None:
    windows = motion_windows(
        [
            FrameCandidate(timestamp=1.0, score=0.8, perceptual_hash="a", source="motion"),
            FrameCandidate(timestamp=1.3, score=0.7, perceptual_hash="b", source="motion"),
            FrameCandidate(timestamp=8.0, score=0.1, perceptual_hash="c", source="motion"),
        ],
        duration_seconds=10,
        threshold=0.5,
    )

    assert windows == [(0.5, 1.8)]
