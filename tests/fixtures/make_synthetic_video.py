"""Generate tiny local-only videos for FFmpeg integration tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def make_synthetic_video(path: Path) -> None:
    """Create two one-second color scenes without committing binary media."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x64:r=10:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x64:r=10:d=1",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
