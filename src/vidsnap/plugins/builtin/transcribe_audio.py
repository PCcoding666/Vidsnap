"""Bounded ASR tool plugin over kernel-owned local audio windows."""

from __future__ import annotations

from pydantic import Field, model_validator
from typing_extensions import Self

from vidsnap.contracts import Evidence, ProviderUsage
from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.base import ToolArgumentError, ToolExecutionContext, ToolResult
from vidsnap.plugins.manifest import PluginManifest
from vidsnap.video.audio import AudioSegment, audio_trace_summary
from vidsnap.video.ports import extract_asr_audio


class TimeWindow(StrictModel):
    """One positive, ordered span of the local media timeline."""

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class TranscribeAudioArgs(StrictModel):
    """At most three probe-relative windows; empty means the full local range."""

    windows: tuple[TimeWindow, ...] = Field(default=(), max_length=3)


def windows_within_duration(windows: tuple[TimeWindow, ...], duration_seconds: float) -> None:
    """Reject any requested window that escapes the probed local duration."""
    for window in windows:
        if window.start_seconds >= duration_seconds or window.end_seconds > duration_seconds:
            raise ToolArgumentError(
                "requested window exceeds the probed media duration: "
                f"[{window.start_seconds}, {window.end_seconds}] > {duration_seconds}"
            )


class TranscribeAudioPlugin:
    """Transcribe bounded local audio windows into stable transcript evidence."""

    manifest = PluginManifest(
        id="vidsnap.tool.transcribe_audio",
        version="1.0.0",
        kind="tool",
        model_visible=True,
    )
    name: str = "transcribe_audio"
    input_model: type[StrictModel] = TranscribeAudioArgs

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        """Run at most three local ASR windows; never echo transcript text outward."""
        if not isinstance(arguments, TranscribeAudioArgs):
            raise TypeError("transcribe_audio requires TranscribeAudioArgs")
        if not context.probe.has_audio or context.recognizer is None:
            return ToolResult(status="skipped")
        duration = context.probe.duration_seconds
        windows = arguments.windows or (TimeWindow(start_seconds=0, end_seconds=duration),)
        windows_within_duration(windows, duration)

        compressed = bool(getattr(context.recognizer, "accepts_compressed_audio", False))
        evidence_ids: list[str] = []
        character_count = 0
        total_usage = ProviderUsage()
        sent: list[AudioSegment] = []
        for index, window in enumerate(windows):
            audio_dir = context.artifact_root / "audio"
            segments = await extract_asr_audio(
                context.media,
                context.source_path,
                audio_dir / f"window-{index:03d}",
                audio_dir / f"window-{index:03d}.wav",
                compressed=compressed,
                start_seconds=window.start_seconds,
                end_seconds=window.end_seconds,
            )
            texts: list[str] = []
            for segment in segments:
                response = await context.recognizer.transcribe(
                    segment.path.read_bytes(), mime_type=segment.mime_type
                )
                texts.append(response.text)
                total_usage = total_usage + response.usage
            sent.extend(segments)
            text = "\n".join(texts)
            evidence_id = context.evidence_sink.next_id("transcript")
            context.evidence_sink.add(
                Evidence(
                    id=evidence_id,
                    start_seconds=window.start_seconds,
                    end_seconds=window.end_seconds,
                    modality="transcript",
                    content=text,
                )
            )
            evidence_ids.append(evidence_id)
            character_count += len(text)

        return ToolResult(
            status="completed",
            evidence_ids=tuple(evidence_ids),
            summary={
                "transcript_count": len(evidence_ids),
                "character_count": character_count,
                **audio_trace_summary(sent),
            },
            usage=total_usage,
        )
