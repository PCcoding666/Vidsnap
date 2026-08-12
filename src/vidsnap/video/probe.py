"""Safe local FFmpeg/ffprobe adapter for reconnaissance and evidence extraction."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from vidsnap.video.sampling import AdaptiveSampler, EvidenceSamplingPolicy, FrameCandidate

_SCENE_TIMESTAMP = re.compile(r"pts_time:(?P<timestamp>\d+(?:\.\d+)?)")


class FFmpegError(RuntimeError):
    """Raised when a local FFmpeg command cannot produce the requested media data."""


@dataclass(frozen=True, slots=True)
class MediaProbe:
    """Minimal local media metadata needed for evidence planning."""

    duration_seconds: float
    fps: float
    width: int
    height: int
    has_audio: bool
    video_codec: str | None = None
    audio_codec: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedFrame:
    """One JPEG evidence file and the timestamp it represents."""

    path: Path
    timestamp: float
    perceptual_hash: str


def parse_scene_timestamps(output: str) -> list[float]:
    """Parse, order, and deduplicate FFmpeg metadata timestamps."""
    return sorted({float(match.group("timestamp")) for match in _SCENE_TIMESTAMP.finditer(output)})


def motion_windows(
    candidates: Sequence[FrameCandidate],
    *,
    duration_seconds: float,
    threshold: float,
) -> list[tuple[float, float]]:
    """Return merged half-second windows around high-motion observations."""
    windows = sorted(
        (
            max(0.0, candidate.timestamp - 0.5),
            min(duration_seconds, candidate.timestamp + 0.5),
        )
        for candidate in candidates
        if candidate.source == "motion" and candidate.score >= threshold
    )
    merged: list[tuple[float, float]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _parse_frame_rate(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _perceptual_hash(frame: bytes) -> str:
    """Compute a tiny deterministic average hash from an 8×8 grayscale frame."""
    if not frame:
        return "empty"
    average = sum(frame) / len(frame)
    bit_string = "".join("1" if pixel >= average else "0" for pixel in frame)
    bits_as_hex = f"{int(bit_string, 2):0{(len(bit_string) + 3) // 4}x}"
    return f"{round(average):03d}-{bits_as_hex}"


class FFmpegMediaPort:
    """Run only local, argument-array FFmpeg commands for one source video."""

    def __init__(
        self,
        *,
        sampler: AdaptiveSampler | None = None,
        policy: EvidenceSamplingPolicy | None = None,
    ) -> None:
        if sampler is not None and policy is not None:
            raise ValueError("provide either sampler or policy, not both")
        self.sampler = sampler or AdaptiveSampler(policy)

    async def probe(self, source: Path) -> MediaProbe:
        """Read video/audio metadata through ffprobe without evaluating input text."""
        stdout = await self._run(
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(source),
        )
        metadata = json.loads(stdout.decode("utf-8"))
        streams = metadata.get("streams", [])
        video_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "video"),
            None,
        )
        if video_stream is None:
            raise FFmpegError("source has no video stream")
        audio_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"),
            None,
        )
        format_metadata = metadata.get("format", {})
        duration = float(format_metadata.get("duration") or video_stream.get("duration") or 0)
        if duration <= 0:
            raise FFmpegError("source has no positive duration")
        return MediaProbe(
            duration_seconds=duration,
            fps=_parse_frame_rate(video_stream.get("r_frame_rate")),
            width=int(video_stream.get("width") or 0),
            height=int(video_stream.get("height") or 0),
            has_audio=audio_stream is not None,
            video_codec=video_stream.get("codec_name"),
            audio_codec=audio_stream.get("codec_name") if audio_stream is not None else None,
        )

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        """Merge coverage, scene, and pixel-difference signals without model tokens."""
        motion_candidates = await self._motion_candidates(source, probe.duration_seconds)
        motion_candidates.extend(
            await self._high_motion_candidates(
                source,
                probe.duration_seconds,
                motion_candidates,
            )
        )
        return self.sampler.merge_candidates(
            duration_seconds=probe.duration_seconds,
            scene_timestamps=await self.scene_timestamps(source),
            motion_candidates=motion_candidates,
        )

    async def scene_timestamps(self, source: Path) -> list[float]:
        """Detect scene transitions with FFmpeg's deterministic scene score."""
        filter_graph = (
            f"select='gt(scene,{self.sampler.policy.scene_threshold})',metadata=print:file=-"
        )
        stdout, stderr = await self._run_with_stderr(
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(source),
            "-vf",
            filter_graph,
            "-an",
            "-f",
            "null",
            "-",
        )
        return parse_scene_timestamps((stdout + stderr).decode("utf-8", errors="replace"))

    async def extract_frames(
        self,
        source: Path,
        candidates: Sequence[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        """Extract only the selected timestamps as local JPEG evidence files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted: list[ExtractedFrame] = []
        for index, candidate in enumerate(sorted(candidates, key=lambda item: item.timestamp)):
            output_path = output_dir / f"frame-{index:03d}-{candidate.timestamp:.3f}.jpg"
            await self._run(
                "ffmpeg",
                "-y",
                "-ss",
                f"{candidate.timestamp:.6f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(output_path),
            )
            if not output_path.exists():
                raise FFmpegError(f"ffmpeg reported success without writing {output_path.name}")
            extracted.append(
                ExtractedFrame(
                    path=output_path,
                    timestamp=candidate.timestamp,
                    perceptual_hash=candidate.perceptual_hash,
                )
            )
        return extracted

    async def extract_timeline_frames(
        self,
        source: Path,
        *,
        fps: int,
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        """Extract a complete fixed-rate timeline with one FFmpeg process."""
        if fps <= 0:
            raise ValueError("timeline fps must be positive")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_pattern = output_dir / "frame-%06d.jpg"
        await self._run(
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"fps={fps}",
            "-q:v",
            "2",
            str(output_pattern),
        )
        frame_paths = sorted(output_dir.glob("frame-*.jpg"))
        if not frame_paths:
            raise FFmpegError("ffmpeg reported success without writing timeline frames")
        return [
            ExtractedFrame(
                path=path,
                timestamp=index / fps,
                perceptual_hash=f"timeline-{index}",
            )
            for index, path in enumerate(frame_paths)
        ]

    async def extract_audio(self, source: Path, output_path: Path) -> Path:
        """Extract 16 kHz mono WAV audio locally for a SpeechRecognizer port."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await self._run(
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        )
        if not output_path.exists():
            raise FFmpegError("ffmpeg reported success without writing audio")
        return output_path

    async def _motion_candidates(
        self,
        source: Path,
        duration_seconds: float,
        *,
        sample_fps: int | None = None,
        start_seconds: float = 0,
        end_seconds: float | None = None,
    ) -> list[FrameCandidate]:
        """Score low-resolution frame differences as a deterministic motion signal."""
        effective_fps = sample_fps or self.sampler.policy.motion_sample_fps
        window_end = end_seconds if end_seconds is not None else duration_seconds
        command = [
            "ffmpeg",
            "-v",
            "error",
        ]
        if start_seconds > 0:
            command.extend(["-ss", f"{start_seconds:.6f}"])
        command.extend(
            [
                "-i",
                str(source),
                "-t",
                f"{max(0.0, window_end - start_seconds):.6f}",
                "-vf",
                f"fps={effective_fps},scale=8:8,format=gray",
                "-f",
                "rawvideo",
                "-",
            ]
        )
        raw_frames = await self._run(*command)
        frame_size = 64
        candidates: list[FrameCandidate] = []
        previous: bytes | None = None
        for index in range(0, len(raw_frames) // frame_size):
            frame = raw_frames[index * frame_size : (index + 1) * frame_size]
            timestamp = min(
                start_seconds + (index + 0.5) / effective_fps,
                window_end,
            )
            difference = (
                0.0
                if previous is None
                else sum(abs(current - prior) for current, prior in zip(frame, previous))
                / (255 * frame_size)
            )
            candidates.append(
                FrameCandidate(
                    timestamp=timestamp,
                    score=difference,
                    perceptual_hash=_perceptual_hash(frame),
                    source="motion",
                )
            )
            previous = frame
        return candidates

    async def _high_motion_candidates(
        self,
        source: Path,
        duration_seconds: float,
        low_rate_candidates: Sequence[FrameCandidate],
    ) -> list[FrameCandidate]:
        """Resample only high-motion windows at the policy's local high frame rate."""
        candidates: list[FrameCandidate] = []
        for start, end in motion_windows(
            low_rate_candidates,
            duration_seconds=duration_seconds,
            threshold=self.sampler.policy.high_motion_threshold,
        ):
            candidates.extend(
                await self._motion_candidates(
                    source,
                    duration_seconds,
                    sample_fps=self.sampler.policy.high_motion_fps,
                    start_seconds=start,
                    end_seconds=end,
                )
            )
        return candidates

    async def _run(self, *arguments: str) -> bytes:
        stdout, _ = await self._run_with_stderr(*arguments)
        return stdout

    async def _run_with_stderr(self, *arguments: str) -> tuple[bytes, bytes]:
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            command = arguments[0] if arguments else "process"
            detail = stderr.decode("utf-8", errors="replace")[-500:]
            raise FFmpegError(f"{command} failed ({process.returncode}): {detail}")
        return stdout, stderr
