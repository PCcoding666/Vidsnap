"""Pure deterministic adaptive-sampling behavior."""

from vidsnap.video.sampling import AdaptiveSampler, FrameCandidate


def test_sampler_preserves_coverage_and_deduplicates_near_identical_frames() -> None:
    candidates = [
        FrameCandidate(timestamp=0.0, score=1.0, perceptual_hash="a"),
        FrameCandidate(timestamp=0.1, score=0.9, perceptual_hash="a"),
        FrameCandidate(timestamp=5.0, score=0.8, perceptual_hash="b"),
        FrameCandidate(timestamp=10.0, score=0.7, perceptual_hash="c"),
    ]

    selected = AdaptiveSampler().select(candidates, max_frames=3)

    assert [item.perceptual_hash for item in selected] == ["a", "b", "c"]
    assert len(selected) <= 3


def test_sampler_retains_start_and_end_coverage_under_a_tight_budget() -> None:
    candidates = [
        FrameCandidate(timestamp=0.0, score=0.1, perceptual_hash="start"),
        FrameCandidate(timestamp=5.0, score=10.0, perceptual_hash="middle"),
        FrameCandidate(timestamp=10.0, score=0.1, perceptual_hash="end"),
    ]

    selected = AdaptiveSampler().select(candidates, max_frames=2)

    assert [item.timestamp for item in selected] == [0.0, 10.0]


def test_sampler_merges_asr_and_ocr_anchors_with_visual_candidates() -> None:
    sampler = AdaptiveSampler()

    merged = sampler.merge_candidates(
        duration_seconds=10,
        scene_timestamps=[2.0],
        motion_candidates=[
            FrameCandidate(timestamp=4.0, score=0.8, perceptual_hash="motion", source="motion")
        ],
        asr_timestamps=[6.0],
        ocr_timestamps=[8.0],
    )

    assert {(candidate.timestamp, candidate.source) for candidate in merged} >= {
        (2.0, "scene"),
        (4.0, "motion"),
        (6.0, "asr"),
        (8.0, "ocr"),
    }
