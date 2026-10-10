"""RED-first Batch 3A tests: bounded publishing probe -> sample -> synthesize -> verify.

These tests specify the publishing policy contract: a fixed phase sequence with a
fixed max_frames=12 sample_evidence call, adapter-private transcript that never
enters RunContext evidence, a strict PublishingDraft schema, and deterministic
verification that only accepts known frame evidence ids. They import
vidsnap.publishing.policy and vidsnap.publishing.task, which do not exist yet.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from vidsnap.contracts import (
    Evidence,
    HarnessPolicy,
    TerminalState,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.publishing.policy import PublishingPolicy
from vidsnap.publishing.task import PublishingDraft, PublishingModelResponse, PublishingTaskAdapter
from vidsnap.runtime import HarnessKernel, RunContext, default_plugin_registry
from vidsnap.video.probe import ExtractedFrame, MediaProbe
from vidsnap.video.sampling import AdaptiveSampler, FrameCandidate

EXPECTED_PHASES = [
    "probe_media",
    "sample_evidence",
    "synthesize_result",
    "verify_claims",
    "terminal",
]

_FRAME_BYTES = b"\xff\xd8\xff\xe0fake-publishing-frame"
ARTICLE_TEXT = "Article body that must never reach the RunBundle."
SUMMARY_TEXT = "Summary body that must never reach the RunBundle."


class FakePublishingFFmpeg:
    """Local FFmpeg double producing a configurable number of frame candidates."""

    def __init__(self, *, candidate_count: int = 3, duration_seconds: float = 8.0) -> None:
        self.candidate_count = candidate_count
        self.duration_seconds = duration_seconds
        self.audio_calls: list[tuple[float, float | None]] = []

    async def probe(self, source: Path) -> MediaProbe:
        del source
        return MediaProbe(
            duration_seconds=self.duration_seconds,
            fps=24.0,
            width=320,
            height=240,
            has_audio=True,
            video_codec="h264",
            audio_codec="aac",
        )

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        del source, probe
        return [
            FrameCandidate(
                timestamp=index + 0.5,
                score=1.0,
                perceptual_hash=f"cand-{index}",
                source="uniform",
            )
            for index in range(self.candidate_count)
        ]

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
            frame_path.write_bytes(_FRAME_BYTES + candidate.perceptual_hash.encode("utf-8"))
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=candidate.timestamp,
                    perceptual_hash=candidate.perceptual_hash,
                )
            )
        return frames

    async def extract_audio(
        self,
        source: Path,
        output_path: Path,
        *,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Path:
        del source
        self.audio_calls.append((start_seconds, end_seconds))
        raise AssertionError("publishing runs must never extract audio")


class FakePublishingModel:
    """Publishing model double that drafts from frames and records the private transcript."""

    def __init__(self) -> None:
        self.draft_calls = 0
        self.observed_transcripts: list[str | None] = []

    async def draft_deliverables(
        self,
        evidence: Sequence[Evidence],
        transcript: str | None,
        probe: MediaProbe,
    ) -> PublishingModelResponse:
        del probe
        self.draft_calls += 1
        self.observed_transcripts.append(transcript)
        frame_ids = tuple(item.id for item in evidence if item.modality == "frame")[:2]
        placeholders = "".join(f"\n\n[[image:{evidence_id}]]" for evidence_id in frame_ids)
        draft = PublishingDraft(
            article=ARTICLE_TEXT + placeholders,
            summary=SUMMARY_TEXT,
            image_evidence_ids=frame_ids,
        )
        return PublishingModelResponse(
            draft=draft, input_tokens=11, output_tokens=7, usage_reported=True
        )


def build_context(tmp_path: Path, *, transcript: str | None, candidate_count: int = 3):
    """Assemble one RunContext with result_writer=None and no agent or recognizer."""
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    model = FakePublishingModel()
    adapter = PublishingTaskAdapter(
        goal=VideoGoal(objective="Produce the publishing package"),
        transcript=transcript,
    )
    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(),
        bundle=bundle,
        task_adapter=adapter,
        task_model=model,
        media=FakePublishingFFmpeg(candidate_count=candidate_count),
        sampler=AdaptiveSampler(),
        agent_model=None,
        recognizer=None,
    )
    return context, model


def make_kernel() -> HarnessKernel:
    return HarnessKernel(policy=PublishingPolicy(), registry=default_plugin_registry())


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


def completed_phases(events: list[dict[str, object]]) -> list[object]:
    return [event["phase"] for event in events if event.get("event_type") == "phase.completed"]


def make_probe() -> MediaProbe:
    return MediaProbe(
        duration_seconds=8.0,
        fps=24.0,
        width=320,
        height=240,
        has_audio=True,
        video_codec="h264",
        audio_codec="aac",
    )


def frame_evidence(evidence_id: str, timestamp: float = 1.0) -> Evidence:
    return Evidence(
        id=evidence_id,
        start_seconds=timestamp,
        end_seconds=timestamp,
        modality="frame",
    )


def non_artifact_bundle_files(run_path: Path) -> list[Path]:
    """Every persisted RunBundle file except raw tool artifacts."""
    return [
        path
        for path in sorted(run_path.rglob("*"))
        if path.is_file() and "artifacts" not in path.relative_to(run_path).parts
    ]


@pytest.mark.asyncio
async def test_publishing_policy_runs_exact_phase_sequence_to_success(tmp_path) -> None:
    context, model = build_context(tmp_path, transcript="spoken words")

    result = await make_kernel().run(context)

    events = read_events(context.bundle.path)
    assert completed_phases(events) == EXPECTED_PHASES
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert model.draft_calls == 1
    assert context.result_writer is None
    assert context.output is not None


@pytest.mark.asyncio
async def test_sample_evidence_frame_cap_is_fixed_at_twelve(tmp_path) -> None:
    context, _model = build_context(tmp_path, transcript=None, candidate_count=15)

    result = await make_kernel().run(context)

    frames = [item for item in context.evidence if item.modality == "frame"]
    assert len(frames) == 12
    assert result.terminal_state is TerminalState.SUCCEEDED


@pytest.mark.asyncio
async def test_transcript_stays_adapter_private(tmp_path) -> None:
    transcript = "adapter-private spoken words"
    context, model = build_context(tmp_path, transcript=transcript)

    await make_kernel().run(context)

    assert not [item for item in context.evidence if item.modality == "transcript"]
    events = read_events(context.bundle.path)
    assert "transcribe_audio" not in completed_phases(events)
    assert model.observed_transcripts == [transcript]

    bundle_files = non_artifact_bundle_files(context.bundle.path)
    assert bundle_files, "expected persisted RunBundle metadata files"
    for path in bundle_files:
        text = path.read_text(encoding="utf-8")
        assert transcript not in text
        assert ARTICLE_TEXT not in text
        assert SUMMARY_TEXT not in text
    assert not (context.bundle.path / "result.json").exists()
    assert isinstance(context.output, PublishingDraft)


def test_draft_schema_and_constructors_reject_surprise_inputs() -> None:
    with pytest.raises(ValidationError):
        PublishingDraft(article="", summary="summary")
    with pytest.raises(ValidationError):
        PublishingDraft(article="article", summary="")
    with pytest.raises(ValidationError):
        PublishingDraft(
            article="article",
            summary="summary",
            image_evidence_ids=("frame-001", "frame-001"),
        )
    with pytest.raises(ValidationError):
        PublishingDraft(
            article="article",
            summary="summary",
            image_evidence_ids=tuple(f"frame-{index:03d}" for index in range(13)),
        )
    for field in ("prompt", "model", "url", "tool", "max_frames"):
        with pytest.raises(ValidationError):
            PublishingDraft(article="article", summary="summary", **{field: "surprise"})

    goal = VideoGoal(objective="Produce the publishing package")
    with pytest.raises(TypeError):
        PublishingPolicy(max_frames=24)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        PublishingTaskAdapter(goal=goal, transcript=None, prompt="surprise")  # type: ignore[call-arg]


def test_draft_requires_at_least_one_image_evidence_id() -> None:
    with pytest.raises(ValidationError, match="image_evidence_ids"):
        PublishingDraft(article="纯文字文章。", summary="summary")
    with pytest.raises(ValidationError, match="at least 1"):
        PublishingDraft(article="文章。", summary="summary", image_evidence_ids=())


def test_draft_rejects_whitespace_only_texts() -> None:
    for text in (" ", "\n\t", "\u3000\u3000"):
        with pytest.raises(ValidationError, match="at least 1"):
            PublishingDraft(
                article=text,
                summary="summary",
                image_evidence_ids=("frame-001",),
            )
        with pytest.raises(ValidationError, match="at least 1"):
            PublishingDraft(
                article="正文 [[image:frame-001]]",
                summary=text,
                image_evidence_ids=("frame-001",),
            )


def test_draft_article_placeholders_must_match_image_evidence_ids() -> None:
    valid_two_images = PublishingDraft(
        article="第一段。\n\n[[image:frame-001]]\n\n第二段。\n\n[[image:frame-002]]\n\n结尾。",
        summary="summary",
        image_evidence_ids=("frame-001", "frame-002"),
    )
    assert valid_two_images.image_evidence_ids == ("frame-001", "frame-002")

    with pytest.raises(ValidationError, match="placeholder"):
        PublishingDraft(
            article="声明了图片但没有占位符。",
            summary="summary",
            image_evidence_ids=("frame-001",),
        )
    with pytest.raises(ValidationError, match="placeholder"):
        PublishingDraft(
            article="未声明的额外占位符 [[image:frame-999]] 和 [[image:frame-001]]",
            summary="summary",
            image_evidence_ids=("frame-001",),
        )
    with pytest.raises(ValidationError, match="placeholder"):
        PublishingDraft(
            article="[[image:frame-001]] 和 [[image:frame-001]]",
            summary="summary",
            image_evidence_ids=("frame-001",),
        )
    with pytest.raises(ValidationError, match="placeholder"):
        PublishingDraft(
            article="顺序颠倒 [[image:frame-002]] 然后 [[image:frame-001]]",
            summary="summary",
            image_evidence_ids=("frame-001", "frame-002"),
        )


def test_verify_rejects_unknown_or_non_frame_image_ids() -> None:
    adapter = PublishingTaskAdapter(
        goal=VideoGoal(objective="Produce the publishing package"),
        transcript=None,
    )
    probe = make_probe()
    evidence = (
        frame_evidence("frame-001"),
        Evidence(
            id="transcript-001",
            start_seconds=0.0,
            end_seconds=8.0,
            modality="transcript",
            content="spoken words",
        ),
    )
    valid = PublishingDraft(
        article="article [[image:frame-001]]", summary="summary", image_evidence_ids=("frame-001",)
    )
    assert adapter.verify(valid, evidence, probe).passed is True

    unknown = PublishingDraft(
        article="article [[image:frame-999]]", summary="summary", image_evidence_ids=("frame-999",)
    )
    assert adapter.verify(unknown, evidence, probe).passed is False

    non_frame = PublishingDraft(
        article="article [[image:transcript-001]]",
        summary="summary",
        image_evidence_ids=("transcript-001",),
    )
    assert adapter.verify(non_frame, evidence, probe).passed is False


@pytest.mark.asyncio
async def test_synthesize_usage_is_recorded_without_result_writer(tmp_path) -> None:
    context, _model = build_context(tmp_path, transcript="spoken words")

    await make_kernel().run(context)

    events = read_events(context.bundle.path)
    synthesize = [
        event
        for event in events
        if event.get("event_type") == "phase.completed"
        and event.get("phase") == "synthesize_result"
    ]
    assert synthesize and synthesize[0]["payload"] == {"input_tokens": 11, "output_tokens": 7}
    assert isinstance(context.output, PublishingDraft)
