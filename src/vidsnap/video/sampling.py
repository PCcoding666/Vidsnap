"""Pure deterministic selection of a compact, grounded evidence pack."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

CandidateSource = Literal["uniform", "scene", "motion", "ocr", "asr"]
VideoKind = Literal["static", "talking", "screencast", "action", "unknown"]

_SOURCE_WEIGHTS: dict[VideoKind, dict[CandidateSource, float]] = {
    "static": {"uniform": 0.8, "scene": 1.2, "motion": 0.6, "ocr": 1.5, "asr": 0.9},
    "talking": {"uniform": 0.8, "scene": 0.8, "motion": 0.6, "ocr": 0.8, "asr": 1.5},
    "screencast": {"uniform": 0.8, "scene": 1.1, "motion": 1.3, "ocr": 1.4, "asr": 1.0},
    "action": {"uniform": 0.8, "scene": 1.1, "motion": 1.5, "ocr": 0.6, "asr": 0.8},
    "unknown": {"uniform": 1.0, "scene": 1.1, "motion": 1.1, "ocr": 1.1, "asr": 1.1},
}


@dataclass(frozen=True, slots=True)
class FrameCandidate:
    """A timestamped candidate produced by a deterministic evidence signal."""

    timestamp: float
    score: float
    perceptual_hash: str
    source: CandidateSource = "uniform"

    def __post_init__(self) -> None:
        if self.timestamp < 0:
            raise ValueError("timestamp must be non-negative")
        if self.score < 0:
            raise ValueError("score must be non-negative")
        if not self.perceptual_hash:
            raise ValueError("perceptual_hash must not be empty")


@dataclass(frozen=True, slots=True)
class EvidenceSamplingPolicy:
    """Fixed limits and sampling rates for the no-model reconnaissance stage."""

    uniform_coverage_points: int = 8
    scene_threshold: float = 0.3
    motion_sample_fps: int = 1
    high_motion_fps: int = 4
    high_motion_threshold: float = 0.25
    max_evidence_frames: int = 96

    def __post_init__(self) -> None:
        if self.uniform_coverage_points < 2:
            raise ValueError("uniform_coverage_points must be at least two")
        if not 0 < self.scene_threshold <= 1:
            raise ValueError("scene_threshold must be in (0, 1]")
        if not 1 <= self.motion_sample_fps <= self.high_motion_fps <= 8:
            raise ValueError("motion sampling rates must be between one and eight fps")
        if not 0 < self.high_motion_threshold <= 1:
            raise ValueError("high_motion_threshold must be in (0, 1]")
        if not 1 <= self.max_evidence_frames <= 96:
            raise ValueError("max_evidence_frames must be between one and 96")


class AdaptiveSampler:
    """Select unique, ordered frames while reserving temporal end coverage."""

    def __init__(
        self,
        policy: EvidenceSamplingPolicy | None = None,
        *,
        video_kind: VideoKind = "unknown",
    ) -> None:
        self.policy = policy or EvidenceSamplingPolicy()
        self.video_kind = video_kind

    def uniform_candidates(self, duration_seconds: float) -> list[FrameCandidate]:
        """Generate deterministic center points that cover the full timeline."""
        if duration_seconds <= 0:
            return []
        count = self.policy.uniform_coverage_points
        return [
            FrameCandidate(
                timestamp=(index + 0.5) * duration_seconds / count,
                score=1.0,
                perceptual_hash=f"coverage-{index}",
                source="uniform",
            )
            for index in range(count)
        ]

    def merge_candidates(
        self,
        *,
        duration_seconds: float,
        scene_timestamps: Sequence[float] = (),
        motion_candidates: Sequence[FrameCandidate] = (),
        asr_timestamps: Sequence[float] = (),
        ocr_timestamps: Sequence[float] = (),
    ) -> list[FrameCandidate]:
        """Combine deterministic visual signals with ASR/OCR anchors on one timeline."""
        if duration_seconds <= 0:
            return []
        candidates = self.uniform_candidates(duration_seconds)
        candidates.extend(
            FrameCandidate(
                timestamp=timestamp,
                score=1.0,
                perceptual_hash=f"scene-{timestamp:.3f}",
                source="scene",
            )
            for timestamp in scene_timestamps
            if 0 <= timestamp <= duration_seconds
        )
        candidates.extend(
            candidate for candidate in motion_candidates if candidate.timestamp <= duration_seconds
        )
        candidates.extend(
            FrameCandidate(
                timestamp=timestamp,
                score=1.0,
                perceptual_hash=f"asr-{timestamp:.3f}",
                source="asr",
            )
            for timestamp in asr_timestamps
            if 0 <= timestamp <= duration_seconds
        )
        candidates.extend(
            FrameCandidate(
                timestamp=timestamp,
                score=1.0,
                perceptual_hash=f"ocr-{timestamp:.3f}",
                source="ocr",
            )
            for timestamp in ocr_timestamps
            if 0 <= timestamp <= duration_seconds
        )
        return candidates

    def select(
        self,
        candidates: Sequence[FrameCandidate],
        max_frames: int | None = None,
    ) -> list[FrameCandidate]:
        """Deduplicate by perceptual hash, reserve end coverage, then rank signals."""
        frame_limit = max_frames if max_frames is not None else self.policy.max_evidence_frames
        if frame_limit < 1:
            raise ValueError("max_frames must be positive")

        unique_candidates = self._deduplicate(candidates)
        if len(unique_candidates) <= frame_limit:
            return unique_candidates
        if frame_limit == 1:
            return [max(unique_candidates, key=self._priority)]

        selected = [unique_candidates[0], unique_candidates[-1]]
        selected_hashes = {candidate.perceptual_hash for candidate in selected}
        remaining = [
            candidate
            for candidate in unique_candidates
            if candidate.perceptual_hash not in selected_hashes
        ]
        remaining.sort(key=self._priority, reverse=True)
        selected.extend(remaining[: frame_limit - len(selected)])
        return sorted(selected, key=lambda candidate: candidate.timestamp)

    def _deduplicate(self, candidates: Sequence[FrameCandidate]) -> list[FrameCandidate]:
        best_by_hash: dict[str, FrameCandidate] = {}
        for candidate in candidates:
            existing = best_by_hash.get(candidate.perceptual_hash)
            if existing is None or self._priority(candidate) > self._priority(existing):
                best_by_hash[candidate.perceptual_hash] = candidate
        return sorted(best_by_hash.values(), key=lambda candidate: candidate.timestamp)

    def _priority(self, candidate: FrameCandidate) -> tuple[float, float]:
        source_weight = _SOURCE_WEIGHTS[self.video_kind][candidate.source]
        return (candidate.score * source_weight, -candidate.timestamp)
