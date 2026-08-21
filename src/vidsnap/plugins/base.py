"""Typed plugin protocols and the bounded tool execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field, JsonValue

from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.models import Evidence, StrictModel
from vidsnap.plugins.manifest import PluginManifest
from vidsnap.providers.asr import SpeechRecognizer
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import MediaProbe
from vidsnap.video.sampling import AdaptiveSampler


class EvidenceSink(Protocol):
    """Kernel-owned allocation and storage of structured evidence items."""

    def next_id(self, prefix: Literal["frame", "transcript"]) -> str:
        """Allocate the next sequential evidence ID for one modality."""

    def add(self, evidence: Evidence) -> str:
        """Persist one evidence item and return its allocated ID."""


@dataclass(frozen=True, slots=True)
class TranscriptionResponse:
    """Transcript text plus structured usage; unreported unless measured."""

    text: str
    usage: ProviderUsage = field(default_factory=lambda: ProviderUsage(reported=False))


class TranscriptionPort(Protocol):
    """Typed transcription result boundary used by the ASR tool plugin."""

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        """Transcribe local audio bytes without persisting them remotely."""


class ToolResult(StrictModel):
    """The bounded outcome of one plugin tool execution."""

    status: Literal["completed", "skipped", "failed"]
    evidence_ids: tuple[str, ...] = ()
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    usage: ProviderUsage = Field(default_factory=lambda: ProviderUsage(reported=False))


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Only the bounded local capabilities one tool invocation may use."""

    source_path: Path
    probe: MediaProbe
    artifact_root: Path
    media: FFmpegPort
    recognizer: TranscriptionPort | None
    sampler: AdaptiveSampler
    evidence_sink: EvidenceSink


class Plugin(Protocol):
    """The minimal identity every registered plugin of any kind must expose."""

    manifest: PluginManifest


@runtime_checkable
class ToolPlugin(Protocol):
    """One registered, model-callable capability with a strict input schema."""

    manifest: PluginManifest
    name: str
    input_model: type[StrictModel]

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        """Run validated arguments against bounded local capabilities."""


class SpeechRecognizerAdapter:
    """Compatibility bridge from the public SpeechRecognizer to TranscriptionPort."""

    def __init__(self, recognizer: SpeechRecognizer) -> None:
        self._recognizer = recognizer

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        text = await self._recognizer.transcribe(audio_bytes, mime_type=mime_type)
        return TranscriptionResponse(text=text)
