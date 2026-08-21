"""The two approved default tool plugins, assembled in stable order."""

from __future__ import annotations

from vidsnap.plugins.base import ToolPlugin
from vidsnap.plugins.builtin.sample_evidence import SampleEvidenceArgs, SampleEvidencePlugin
from vidsnap.plugins.builtin.transcribe_audio import (
    TimeWindow,
    TranscribeAudioArgs,
    TranscribeAudioPlugin,
)

__all__ = [
    "SampleEvidenceArgs",
    "SampleEvidencePlugin",
    "TimeWindow",
    "TranscribeAudioArgs",
    "TranscribeAudioPlugin",
    "default_tool_plugins",
]


def default_tool_plugins() -> tuple[ToolPlugin, ...]:
    """Return exactly the two model-visible default tools in stable order."""
    return (TranscribeAudioPlugin(), SampleEvidencePlugin())
