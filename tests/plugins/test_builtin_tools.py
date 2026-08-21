"""Bounded default tool plugins: strict arguments, stable evidence IDs."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from vidsnap.contracts import Evidence, ProviderUsage
from vidsnap.plugins.base import ToolExecutionContext, ToolResult, TranscriptionResponse
from vidsnap.plugins.builtin import default_tool_plugins
from vidsnap.plugins.builtin.sample_evidence import SampleEvidenceArgs, SampleEvidencePlugin
from vidsnap.plugins.builtin.transcribe_audio import TranscribeAudioArgs, TranscribeAudioPlugin
from vidsnap.video.probe import ExtractedFrame, MediaProbe
from vidsnap.video.sampling import AdaptiveSampler, FrameCandidate


class RecordingEvidenceSink:
    def __init__(self) -> None:
        self.items: list[Evidence] = []
        self.counts = {"frame": 0, "transcript": 0}

    def next_id(self, prefix: Literal["frame", "transcript"]) -> str:
        self.counts[prefix] += 1
        return f"{prefix}-{self.counts[prefix]:03d}"

    def add(self, evidence: Evidence) -> str:
        self.items.append(evidence)
        return evidence.id


class FakeWindowMedia:
    def __init__(self) -> None:
        self.sampled_timestamps: list[float] = []

    async def visual_candidates(self, source, probe):
        del source, probe
        return [
            FrameCandidate(timestamp=value, score=1, perceptual_hash=str(value))
            for value in (1.0, 4.0, 6.0, 9.0)
        ]

    async def extract_frames(self, source, candidates, output_dir):
        del source
        output_dir.mkdir(parents=True)
        self.sampled_timestamps = [item.timestamp for item in candidates]
        frames = []
        for index, item in enumerate(candidates):
            path = output_dir / f"{index}.jpg"
            path.write_bytes(b"frame")
            frames.append(
                ExtractedFrame(
                    path=path,
                    timestamp=item.timestamp,
                    perceptual_hash=item.perceptual_hash,
                )
            )
        return frames


class FakeTranscribeMedia:
    def __init__(self) -> None:
        self.requests: list[tuple[float, float | None]] = []

    async def extract_audio(self, source, output_path, *, start_seconds=0.0, end_seconds=None):
        del source
        self.requests.append((start_seconds, end_seconds))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"audio")
        return output_path


class FakeTranscriptionPort:
    def __init__(self, usage: ProviderUsage | None = None) -> None:
        self.usage = usage or ProviderUsage(reported=False)
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav"):
        self.calls.append((audio_bytes, mime_type))
        return TranscriptionResponse(text="spoken words", usage=self.usage)


def make_context(
    tmp_path: Path,
    *,
    media,
    recognizer,
    has_audio: bool = True,
    duration_seconds: float = 10.0,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        source_path=tmp_path / "video.mp4",
        probe=MediaProbe(
            duration_seconds=duration_seconds,
            fps=24,
            width=640,
            height=360,
            has_audio=has_audio,
        ),
        artifact_root=tmp_path / "artifacts",
        media=media,
        recognizer=recognizer,
        sampler=AdaptiveSampler(),
        evidence_sink=RecordingEvidenceSink(),
    )


def test_tool_arguments_reject_out_of_bounds_windows() -> None:
    with pytest.raises(ValidationError):
        TranscribeAudioArgs(windows=[{"start_seconds": 8, "end_seconds": 2}])
    with pytest.raises(ValidationError):
        SampleEvidenceArgs(max_frames=97)
    with pytest.raises(ValidationError):
        SampleEvidenceArgs(windows=[{"start_seconds": 0, "end_seconds": 1}] * 4)
    with pytest.raises(ValidationError):
        SampleEvidenceArgs(max_frames=0)


@pytest.mark.asyncio
async def test_visual_tool_samples_only_requested_window(tmp_path) -> None:
    media = FakeWindowMedia()
    context = make_context(tmp_path, media=media, recognizer=None, has_audio=False)
    result = await SampleEvidencePlugin().execute(
        SampleEvidenceArgs(windows=({"start_seconds": 4, "end_seconds": 6},), max_frames=2),
        context,
    )
    assert result.status == "completed"
    assert result.evidence_ids == ("frame-001", "frame-002")
    assert media.sampled_timestamps == [4.0, 6.0]
    frames = context.evidence_sink.items
    assert [item.id for item in frames] == ["frame-001", "frame-002"]
    assert [item.start_seconds for item in frames] == [4.0, 6.0]
    assert all(item.modality == "frame" for item in frames)
    assert all(item.artifact_path is not None and item.artifact_path.exists() for item in frames)
    assert result.summary["frame_count"] == 2
    assert "path" not in str(result.summary)


@pytest.mark.asyncio
async def test_visual_tool_empty_windows_cover_full_local_range(tmp_path) -> None:
    media = FakeWindowMedia()
    context = make_context(tmp_path, media=media, recognizer=None, has_audio=False)
    result = await SampleEvidencePlugin().execute(SampleEvidenceArgs(max_frames=8), context)
    assert result.evidence_ids == ("frame-001", "frame-002", "frame-003", "frame-004")
    assert media.sampled_timestamps == [1.0, 4.0, 6.0, 9.0]


@pytest.mark.asyncio
async def test_visual_tool_rejects_windows_beyond_probe_duration(tmp_path) -> None:
    context = make_context(tmp_path, media=FakeWindowMedia(), recognizer=None, has_audio=False)
    with pytest.raises(ValueError, match="duration"):
        await SampleEvidencePlugin().execute(
            SampleEvidenceArgs(windows=({"start_seconds": 9, "end_seconds": 20},)),
            context,
        )


@pytest.mark.asyncio
async def test_transcribe_tool_skips_without_audio_or_recognizer(tmp_path) -> None:
    media = FakeTranscribeMedia()
    silent = make_context(
        tmp_path, media=media, recognizer=FakeTranscriptionPort(), has_audio=False
    )
    skipped = await TranscribeAudioPlugin().execute(TranscribeAudioArgs(), silent)
    assert skipped.status == "skipped"
    assert skipped.evidence_ids == ()
    assert media.requests == []

    no_port = make_context(tmp_path, media=media, recognizer=None)
    assert (
        await TranscribeAudioPlugin().execute(TranscribeAudioArgs(), no_port)
    ).status == "skipped"
    assert media.requests == []


@pytest.mark.asyncio
async def test_transcribe_tool_allocates_stable_transcript_ids_and_usage(tmp_path) -> None:
    media = FakeTranscribeMedia()
    recognizer = FakeTranscriptionPort(usage=ProviderUsage(input_tokens=3, output_tokens=2))
    context = make_context(tmp_path, media=media, recognizer=recognizer)
    result = await TranscribeAudioPlugin().execute(
        TranscribeAudioArgs(
            windows=({"start_seconds": 1, "end_seconds": 3}, {"start_seconds": 5, "end_seconds": 6})
        ),
        context,
    )
    assert result.status == "completed"
    assert result.evidence_ids == ("transcript-001", "transcript-002")
    assert media.requests == [(1.0, 3.0), (5.0, 6.0)]
    assert len(recognizer.calls) == 2
    assert all(payload == b"audio" and mime == "audio/wav" for payload, mime in recognizer.calls)
    transcripts = context.evidence_sink.items
    assert [item.id for item in transcripts] == ["transcript-001", "transcript-002"]
    assert [(item.start_seconds, item.end_seconds) for item in transcripts] == [
        (1.0, 3.0),
        (5.0, 6.0),
    ]
    assert all(item.content == "spoken words" for item in transcripts)
    assert result.usage == ProviderUsage(input_tokens=6, output_tokens=4)
    assert "spoken" not in str(result.summary)
    assert result.summary["transcript_count"] == 2
    assert result.summary["character_count"] == 24


@pytest.mark.asyncio
async def test_transcribe_tool_empty_windows_transcribe_full_range(tmp_path) -> None:
    media = FakeTranscribeMedia()
    context = make_context(tmp_path, media=media, recognizer=FakeTranscriptionPort())
    result = await TranscribeAudioPlugin().execute(TranscribeAudioArgs(), context)
    assert media.requests == [(0.0, 10.0)]
    assert result.evidence_ids == ("transcript-001",)
    assert result.usage.reported is False


@pytest.mark.asyncio
async def test_transcribe_tool_rejects_windows_beyond_probe_duration(tmp_path) -> None:
    context = make_context(
        tmp_path, media=FakeTranscribeMedia(), recognizer=FakeTranscriptionPort()
    )
    with pytest.raises(ValueError, match="duration"):
        await TranscribeAudioPlugin().execute(
            TranscribeAudioArgs(windows=({"start_seconds": 9, "end_seconds": 11},)),
            context,
        )


def test_default_tool_plugins_are_exactly_the_two_model_visible_tools() -> None:
    plugins = default_tool_plugins()
    assert [plugin.name for plugin in plugins] == ["transcribe_audio", "sample_evidence"]
    for plugin in plugins:
        assert plugin.manifest.kind == "tool"
        assert plugin.manifest.model_visible is True
        assert plugin.manifest.id == f"vidsnap.tool.{plugin.name}"
        result = ToolResult(status="completed")
        assert result.usage.reported is False
