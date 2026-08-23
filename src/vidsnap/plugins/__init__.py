"""Plugin contracts, registry, and controlled discovery for VidSnap."""

from vidsnap.plugins.base import (
    EvidenceSink,
    Plugin,
    SpeechRecognizerAdapter,
    ToolExecutionContext,
    ToolPlugin,
    ToolResult,
    TranscriptionPort,
    TranscriptionResponse,
)
from vidsnap.plugins.discovery import discover_allowed_plugins
from vidsnap.plugins.manifest import PluginManifest
from vidsnap.plugins.registry import PluginRegistry

__all__ = [
    "EvidenceSink",
    "Plugin",
    "PluginManifest",
    "PluginRegistry",
    "SpeechRecognizerAdapter",
    "ToolExecutionContext",
    "ToolPlugin",
    "ToolResult",
    "TranscriptionPort",
    "TranscriptionResponse",
    "discover_allowed_plugins",
]
