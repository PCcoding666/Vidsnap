"""Deterministic, offline fakes for the runtime kernel ports.

These fakes implement the complete current shapes of FFmpegPort, VideoModelPort,
AgentModelPort, and TranscriptionPort without any network, subprocess, or credential
access. They exist so the fixed-policy kernel tests can drive a full bounded run
against in-memory, reproducible behavior.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from vidsnap.contracts import (
    Claim,
    Evidence,
    EvidenceReference,
    ProviderUsage,
    VideoAnalysisResult,
    VideoGoal,
)
from vidsnap.contracts.agent import AgentDecision
from vidsnap.plugins.base import TranscriptionResponse
from vidsnap.providers.base import (
    AgentDecisionResponse,
    AgentStepRequest,
    ModelResponse,
)
from vidsnap.video.probe import ExtractedFrame, MediaProbe
from vidsnap.video.sampling import FrameCandidate

_FRAME_BYTES = b"\xff\xd8\xff\xe0fake-frame"
_AUDIO_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"


class FakeFFmpeg:
    """In-memory FFmpegPort that writes tiny local artifacts and records calls."""

    def __init__(self, *, has_audio: bool = True, duration_seconds: float = 8.0) -> None:
        self.has_audio = has_audio
        self.duration_seconds = duration_seconds
        self.probe_calls = 0
        self.candidate_calls = 0
        self.extracted_frame_calls = 0
        self.timeline_calls = 0
        self.audio_calls: list[tuple[float, float | None]] = []

    async def probe(self, source: Path) -> MediaProbe:
        del source
        self.probe_calls += 1
        return MediaProbe(
            duration_seconds=self.duration_seconds,
            fps=24.0,
            width=320,
            height=240,
            has_audio=self.has_audio,
            video_codec="h264",
            audio_codec="aac" if self.has_audio else None,
        )

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        del source
        self.candidate_calls += 1
        return [
            FrameCandidate(timestamp=1.0, score=1.0, perceptual_hash="cand-1.0", source="uniform"),
            FrameCandidate(timestamp=3.0, score=1.0, perceptual_hash="cand-3.0", source="uniform"),
            FrameCandidate(timestamp=5.0, score=1.0, perceptual_hash="cand-5.0", source="scene"),
        ]

    async def extract_frames(
        self,
        source: Path,
        candidates: Sequence[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        del source
        self.extracted_frame_calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        frames: list[ExtractedFrame] = []
        for index, candidate in enumerate(sorted(candidates, key=lambda item: item.timestamp)):
            frame_path = output_dir / f"frame-{index:03d}-{candidate.timestamp:.3f}.jpg"
            frame_path.write_bytes(_FRAME_BYTES + candidate.perceptual_hash.encode("utf-8"))
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=candidate.timestamp,
                    perceptual_hash=candidate.perceptual_hash,
                )
            )
        return frames

    async def extract_timeline_frames(
        self,
        source: Path,
        *,
        fps: int,
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        del source
        self.timeline_calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        count = max(1, int(self.duration_seconds * fps))
        frames: list[ExtractedFrame] = []
        for index in range(count):
            frame_path = output_dir / f"timeline-{index:06d}.jpg"
            frame_path.write_bytes(_FRAME_BYTES)
            frames.append(
                ExtractedFrame(
                    path=frame_path, timestamp=index / fps, perceptual_hash=f"tl-{index}"
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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_AUDIO_BYTES)
        return output_path


class OverproducingFFmpeg(FakeFFmpeg):
    """FFmpegPort fake whose extract_frames returns more frames than candidates given."""

    def __init__(self, *, extra_frames: int = 2, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.extra_frames = extra_frames

    async def extract_frames(
        self,
        source: Path,
        candidates: Sequence[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        frames = await super().extract_frames(source, candidates, output_dir)
        for index in range(self.extra_frames):
            frame_path = output_dir / f"smuggled-{index:03d}.jpg"
            frame_path.write_bytes(_FRAME_BYTES + f"smuggled-{index}".encode())
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=7.0 + index,
                    perceptual_hash=f"smuggled-{index}",
                )
            )
        return frames


class FakeVideoModel:
    """VideoModelPort fake that grounds every claim in the captured evidence."""

    def __init__(self) -> None:
        self.analyze_calls = 0

    async def analyze_evidence(
        self,
        evidence: Sequence[Evidence],
        goal: VideoGoal,
    ) -> ModelResponse:
        del goal
        self.analyze_calls += 1
        claims = [
            Claim(
                text=f"Observation grounded in evidence {item.id}",
                evidence=[EvidenceReference(evidence_id=item.id)],
                confidence=0.9,
            )
            for item in evidence
        ]
        result = VideoAnalysisResult(
            summary="Deterministic summary anchored to captured local evidence.",
            claims=claims,
        )
        return ModelResponse(result=result, input_tokens=11, output_tokens=7, usage_reported=True)


class FakeAgentModel:
    """AgentModelPort fake; a fixed policy must never ask it for a decision."""

    def __init__(self) -> None:
        self.decide_next_calls = 0

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        del request
        self.decide_next_calls += 1
        decision = AgentDecision(
            kind="final",
            output={"summary": "Unexpected agentic decision in a fixed-policy run."},
        )
        return AgentDecisionResponse(decision=decision, usage=ProviderUsage(reported=False))


class FakeTranscriber:
    """TranscriptionPort fake that returns a fixed transcript and records calls."""

    def __init__(self, *, text: str = "deterministic spoken content") -> None:
        self.text = text
        self.calls: list[tuple[int, str]] = []

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        self.calls.append((len(audio_bytes), mime_type))
        return TranscriptionResponse(
            text=self.text,
            usage=ProviderUsage(input_bytes=len(audio_bytes), input_tokens=2, output_tokens=3),
        )


class LegacyFakeRecognizer:
    """Public SpeechRecognizer fake returning a plain string transcript."""

    def __init__(self, *, text: str = "legacy spoken content") -> None:
        self.text = text
        self.calls: list[tuple[int, str]] = []

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        self.calls.append((len(audio_bytes), mime_type))
        return self.text


class CancellingTranscriber(FakeTranscriber):
    """TranscriptionPort fake that raises asyncio.CancelledError on every call."""

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        del audio_bytes, mime_type
        raise asyncio.CancelledError()
