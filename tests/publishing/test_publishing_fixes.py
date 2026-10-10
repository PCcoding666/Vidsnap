"""RED-first tests for the two publishing-specific field fixes.

Fix 1: long-article publishing requests must use a fixed, bounded 600-second
request timeout on the default Qwen client, independent of the global
HarnessConfig 120-second default and not selectable by the model or the CLI.

Fix 2: publishing must sample with the talking-video strategy so uniform
timeline coverage outranks an opening motion peak, reproducing the failed
72-minute podcast run where 10 of 12 evidence frames landed in the first
19 seconds. The global AdaptiveSampler default must stay "unknown".

Fix 3: a real retry still selected mostly opening frames because uniform and
scene candidates share one weight for talking videos, so a dense opening
scene cluster displaced the uniform coverage points. Talking selection must
keep every uniform coverage point no matter how many scene timestamps cluster
in the opening seconds, while the unknown default keeps its existing ranking.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from tests.publishing.test_policy import FakePublishingModel
from vidsnap.config import HarnessConfig
from vidsnap.contracts import Evidence, TerminalState
from vidsnap.providers.qwen import QwenCompatibleClient
from vidsnap.publishing.service import (
    PUBLISHING_REQUEST_TIMEOUT_SECONDS,
    build_publishing_model,
    publish_video,
)
from vidsnap.video.probe import ExtractedFrame, MediaProbe
from vidsnap.video.sampling import AdaptiveSampler, FrameCandidate

LOCAL_TEST_KEY = "NONSECRET_TEST_MARKER_FIXED_LOCAL_KEY"

_PODCAST_DURATION_SECONDS = 4335.0
_MOTION_TIMESTAMPS = (
    0.5,
    0.875,
    1.75,
    3.208333,
    4.125,
    7.75,
    8.791667,
    11.625,
    15.041667,
    17.75,
)
_OPENING_SCENE_TIMESTAMPS = (
    0.5,
    0.875,
    1.75,
    3.208333,
    4.125,
    7.75,
    8.791667,
    11.625,
    15.041667,
    17.75,
    18.875,
)
_TAIL_SCENE_TIMESTAMP = 4322.5


class PodcastMotionFFmpeg:
    """FFmpeg double replaying the failed run: high-scoring motion in the opening."""

    async def probe(self, source: Path) -> MediaProbe:
        del source
        return MediaProbe(
            duration_seconds=_PODCAST_DURATION_SECONDS,
            fps=24.0,
            width=320,
            height=240,
            has_audio=True,
            video_codec="h264",
            audio_codec="aac",
        )

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        del source
        candidates = [
            FrameCandidate(
                timestamp=(index + 0.5) * probe.duration_seconds / 8,
                score=1.0,
                perceptual_hash=f"coverage-{index}",
                source="uniform",
            )
            for index in range(8)
        ]
        candidates.extend(
            FrameCandidate(
                timestamp=timestamp,
                score=1.3,
                perceptual_hash=f"motion-{timestamp:.3f}",
                source="motion",
            )
            for timestamp in _MOTION_TIMESTAMPS
        )
        return candidates

    async def extract_frames(
        self,
        source: Path,
        candidates: Sequence[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        del source
        output_dir.mkdir(parents=True, exist_ok=True)
        frames: list[ExtractedFrame] = []
        for index, candidate in enumerate(sorted(candidates, key=lambda item: item.timestamp)):
            frame_path = output_dir / f"frame-{index:03d}.jpg"
            frame_path.write_bytes(b"podcast-frame-" + candidate.perceptual_hash.encode("utf-8"))
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=candidate.timestamp,
                    perceptual_hash=candidate.perceptual_hash,
                )
            )
        return frames

    async def extract_audio(self, source: Path, output_path: Path, **kwargs) -> Path:
        del source, output_path, kwargs
        raise AssertionError("publishing runs must never extract audio")


def scene_cluster_candidates() -> list[FrameCandidate]:
    """Merged candidate list replaying the real retry: uniform, scene cluster, motion."""
    return AdaptiveSampler().merge_candidates(
        duration_seconds=_PODCAST_DURATION_SECONDS,
        scene_timestamps=(*_OPENING_SCENE_TIMESTAMPS, _TAIL_SCENE_TIMESTAMP),
        motion_candidates=[
            FrameCandidate(
                timestamp=timestamp,
                score=0.9,
                perceptual_hash=f"motion-{timestamp:.3f}",
                source="motion",
            )
            for timestamp in _MOTION_TIMESTAMPS
        ],
    )


class PodcastSceneClusterFFmpeg:
    """FFmpeg double replaying the real retry: dense opening scene transitions."""

    async def probe(self, source: Path) -> MediaProbe:
        del source
        return MediaProbe(
            duration_seconds=_PODCAST_DURATION_SECONDS,
            fps=24.0,
            width=320,
            height=240,
            has_audio=True,
            video_codec="h264",
            audio_codec="aac",
        )

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        del source, probe
        return scene_cluster_candidates()

    async def extract_frames(
        self,
        source: Path,
        candidates: Sequence[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        del source
        output_dir.mkdir(parents=True, exist_ok=True)
        frames: list[ExtractedFrame] = []
        for index, candidate in enumerate(sorted(candidates, key=lambda item: item.timestamp)):
            frame_path = output_dir / f"frame-{index:03d}.jpg"
            frame_path.write_bytes(b"podcast-frame-" + candidate.perceptual_hash.encode("utf-8"))
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=candidate.timestamp,
                    perceptual_hash=candidate.perceptual_hash,
                )
            )
        return frames

    async def extract_audio(self, source: Path, output_path: Path, **kwargs) -> Path:
        del source, output_path, kwargs
        raise AssertionError("publishing runs must never extract audio")


class RecordingPublishingModel(FakePublishingModel):
    """Model double that records the frame evidence timestamps handed to drafting."""

    def __init__(self) -> None:
        super().__init__()
        self.observed_frame_timestamps: list[float] = []

    async def draft_deliverables(
        self,
        evidence: Sequence[Evidence],
        transcript: str | None,
        probe: MediaProbe,
    ):
        self.observed_frame_timestamps = sorted(
            item.start_seconds for item in evidence if item.modality == "frame"
        )
        return await super().draft_deliverables(evidence, transcript, probe)


def podcast_inputs(tmp_path: Path) -> dict[str, Path]:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    video = tmp_path / "podcast.mp4"
    video.write_bytes(b"deterministic-local-video-bytes")
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text("播客转录第一句。\n第二句。", encoding="utf-8")
    return {
        "video": video,
        "transcript_path": transcript_path,
        "run_dir": tmp_path / "outside" / "run",
        "output_dir": tmp_path / "outside" / "publish",
        "repository_root": repository_root,
    }


def uniform_coverage_timestamps() -> set[float]:
    return {(index + 0.5) * _PODCAST_DURATION_SECONDS / 8 for index in range(8)}


def test_publishing_default_qwen_client_uses_fixed_600_second_timeout() -> None:
    assert PUBLISHING_REQUEST_TIMEOUT_SECONDS == 600.0
    assert 120.0 < PUBLISHING_REQUEST_TIMEOUT_SECONDS < 900.0
    assert HarnessConfig().request_timeout_seconds == 120.0

    for config in (
        HarnessConfig(api_key=LOCAL_TEST_KEY),
        HarnessConfig(api_key=LOCAL_TEST_KEY, request_timeout_seconds=30.0),
    ):
        client = build_publishing_model(config)
        assert isinstance(client, QwenCompatibleClient)
        assert client.timeout_seconds == 600.0


@pytest.mark.asyncio
async def test_publishing_sampler_is_created_with_talking_video_kind(tmp_path, monkeypatch) -> None:
    creations: list[dict[str, object]] = []

    def recording_sampler(*args, **kwargs):
        creations.append(kwargs)
        return AdaptiveSampler(*args, **kwargs)

    monkeypatch.setattr("vidsnap.publishing.service.AdaptiveSampler", recording_sampler)

    result = await publish_video(
        config=HarnessConfig(api_key=LOCAL_TEST_KEY),
        media=PodcastMotionFFmpeg(),
        model=FakePublishingModel(),
        **podcast_inputs(tmp_path),
    )

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert creations, "publishing must construct its own AdaptiveSampler"
    assert creations[0].get("video_kind") == "talking"


@pytest.mark.asyncio
async def test_publishing_run_selects_full_uniform_coverage_across_mid_video(tmp_path) -> None:
    model = RecordingPublishingModel()

    result = await publish_video(
        config=HarnessConfig(api_key=LOCAL_TEST_KEY),
        media=PodcastMotionFFmpeg(),
        model=model,
        **podcast_inputs(tmp_path),
    )

    assert result.terminal_state is TerminalState.SUCCEEDED
    selected = model.observed_frame_timestamps
    assert len(selected) == 12
    assert uniform_coverage_timestamps() <= set(selected)
    assert any(timestamp >= 2000.0 for timestamp in selected), (
        "selected frames must span the middle of a long podcast"
    )


def test_talking_selection_semantics_uniform_beats_opening_motion_peak() -> None:
    candidates = AdaptiveSampler(video_kind="talking").merge_candidates(
        duration_seconds=_PODCAST_DURATION_SECONDS,
        motion_candidates=[
            FrameCandidate(
                timestamp=timestamp,
                score=1.3,
                perceptual_hash=f"motion-{timestamp:.3f}",
                source="motion",
            )
            for timestamp in _MOTION_TIMESTAMPS
        ],
    )
    uniform_timestamps = uniform_coverage_timestamps()

    talking_selected = AdaptiveSampler(video_kind="talking").select(candidates, max_frames=12)
    assert len(talking_selected) == 12
    assert uniform_timestamps <= {candidate.timestamp for candidate in talking_selected}
    assert any(candidate.timestamp >= 2000.0 for candidate in talking_selected)

    unknown_selected = AdaptiveSampler(video_kind="unknown").select(candidates, max_frames=12)
    assert uniform_timestamps - {candidate.timestamp for candidate in unknown_selected}, (
        "the unknown-kind default must reproduce the field failure so the RED test is honest"
    )
    assert AdaptiveSampler().video_kind == "unknown"


def test_talking_selection_uniform_survives_opening_scene_cluster() -> None:
    candidates = scene_cluster_candidates()
    uniform_timestamps = uniform_coverage_timestamps()

    talking_selected = AdaptiveSampler(video_kind="talking").select(candidates, max_frames=12)

    assert len(talking_selected) == 12
    selected_timestamps = {candidate.timestamp for candidate in talking_selected}
    assert uniform_timestamps <= selected_timestamps, (
        "an opening scene cluster must never displace uniform timeline coverage"
    )
    assert _TAIL_SCENE_TIMESTAMP in selected_timestamps
    assert sum(1 for timestamp in selected_timestamps if timestamp >= 2000.0) >= 4, (
        "talking selection must keep mid and late timeline coverage"
    )

    assert AdaptiveSampler().video_kind == "unknown"


@pytest.mark.asyncio
async def test_publishing_run_keeps_uniform_coverage_under_opening_scene_cluster(tmp_path) -> None:
    model = RecordingPublishingModel()

    result = await publish_video(
        config=HarnessConfig(api_key=LOCAL_TEST_KEY),
        media=PodcastSceneClusterFFmpeg(),
        model=model,
        **podcast_inputs(tmp_path),
    )

    assert result.terminal_state is TerminalState.SUCCEEDED
    selected = model.observed_frame_timestamps
    assert len(selected) == 12
    assert uniform_coverage_timestamps() <= set(selected), (
        "publishing evidence must keep all eight uniform coverage points"
    )
    assert _TAIL_SCENE_TIMESTAMP in selected
    assert sum(1 for timestamp in selected if timestamp >= 2000.0) >= 4
