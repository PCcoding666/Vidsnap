"""Template example: a deterministic zero-argument video metadata tool plugin.

This module demonstrates the minimal, side-effect-free shape of a VidSnap tool
plugin. It derives its entire output from the bounded ``MediaProbe`` already
present on the execution context, so it performs no I/O and issues no model
calls. It is meant to be copied and adapted, not wired into the core runtime.
"""

from __future__ import annotations

from pydantic import JsonValue

from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.base import ToolExecutionContext, ToolPlugin, ToolResult
from vidsnap.plugins.manifest import PluginManifest


class VideoMetadataInput(StrictModel):
    """Empty strict input; the tool takes no model-supplied arguments."""


class _VideoMetadataPlugin:
    """Runtime tool plugin that reports the probed container/stream metadata."""

    def __init__(self) -> None:
        self.manifest = PluginManifest(
            id="video-metadata",
            version="0.1.0",
            kind="tool",
            provides=("video_metadata",),
            requires=(),
            model_visible=True,
        )
        self.name = "video_metadata"
        self.input_model = VideoMetadataInput

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        """Return probe-derived metadata without evidence, artifacts, or model calls."""
        probe = context.probe
        summary: dict[str, JsonValue] = {
            "duration_seconds": probe.duration_seconds,
            "fps": probe.fps,
            "width": probe.width,
            "height": probe.height,
            "has_audio": probe.has_audio,
            "video_codec": probe.video_codec,
            "audio_codec": probe.audio_codec,
        }
        return ToolResult(
            status="completed",
            evidence_ids=(),
            summary=summary,
            usage=ProviderUsage(reported=False),
        )


def TOOL() -> ToolPlugin:
    """Build one deterministic, zero-argument ``video_metadata`` tool plugin."""
    return _VideoMetadataPlugin()
