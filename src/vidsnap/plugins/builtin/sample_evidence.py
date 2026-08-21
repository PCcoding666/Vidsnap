"""Bounded visual sampling tool plugin over kernel-owned local frames."""

from __future__ import annotations

from pydantic import Field

from vidsnap.contracts import Evidence
from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.base import ToolExecutionContext, ToolResult
from vidsnap.plugins.builtin.transcribe_audio import TimeWindow, windows_within_duration
from vidsnap.plugins.manifest import PluginManifest


class SampleEvidenceArgs(StrictModel):
    """Zero-to-three local windows and a frame cap; no paths, URLs, or encoders."""

    windows: tuple[TimeWindow, ...] = Field(default=(), max_length=3)
    max_frames: int = Field(default=12, ge=1, le=96)


class SampleEvidencePlugin:
    """Sample deterministic local frame evidence inside requested time windows."""

    manifest = PluginManifest(
        id="vidsnap.tool.sample_evidence",
        version="1.0.0",
        kind="tool",
        model_visible=True,
    )
    name: str = "sample_evidence"
    input_model: type[StrictModel] = SampleEvidenceArgs

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        """Filter candidates to the requested windows and extract bounded frames."""
        if not isinstance(arguments, SampleEvidenceArgs):
            raise TypeError("sample_evidence requires SampleEvidenceArgs")
        duration = context.probe.duration_seconds
        windows_within_duration(arguments.windows, duration)

        candidates = await context.media.visual_candidates(context.source_path, context.probe)
        if arguments.windows:
            candidates = [
                candidate
                for candidate in candidates
                if any(
                    window.start_seconds <= candidate.timestamp <= window.end_seconds
                    for window in arguments.windows
                )
            ]
        if not candidates:
            return ToolResult(status="completed", summary={"frame_count": 0})

        selected = context.sampler.select(candidates, max_frames=arguments.max_frames)
        frames = await context.media.extract_frames(
            context.source_path,
            selected,
            context.artifact_root / "frames",
        )

        evidence_ids: list[str] = []
        for frame in frames:
            evidence_id = context.evidence_sink.next_id("frame")
            context.evidence_sink.add(
                Evidence(
                    id=evidence_id,
                    start_seconds=frame.timestamp,
                    end_seconds=frame.timestamp,
                    modality="frame",
                    artifact_path=frame.path,
                )
            )
            evidence_ids.append(evidence_id)

        return ToolResult(
            status="completed",
            evidence_ids=tuple(evidence_ids),
            summary={"frame_count": len(evidence_ids)},
        )
