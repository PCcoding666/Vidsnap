"""Compatibility facade exposing LoopSpec skills through the plugin registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from vidsnap.contracts import LoopSpec
from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.base import ToolExecutionContext, ToolResult
from vidsnap.plugins.manifest import PluginManifest
from vidsnap.plugins.registry import PluginRegistry

SkillHandler = Callable[[Any], Awaitable[None]]


class _LegacySkill:
    """Stores one LoopSpec-approved handler as an internal plugin entry."""

    def __init__(self, name: str, handler: SkillHandler) -> None:
        self.name = name
        self.handler = handler
        self.manifest = PluginManifest(
            id=f"vidsnap.skill.{name}",
            version="1.0.0",
            kind="tool",
        )
        self.input_model: type[StrictModel] = StrictModel

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        raise RuntimeError("legacy skills are invoked through SkillRegistry.run")


class SkillRegistry:
    """Register and invoke only skills named in the current LoopSpec.

    Deprecated for one release: storage now runs through PluginRegistry, and
    new code should register Tool Plugins instead of harness-bound methods.
    """

    def __init__(self, loop_spec: LoopSpec) -> None:
        self._allowed = loop_spec.allowed_skills
        self._plugins = PluginRegistry(
            allowed_ids={f"vidsnap.skill.{name}" for name in self._allowed}
        )
        self._handlers: dict[str, SkillHandler] = {}

    def register(self, name: str, handler: SkillHandler) -> None:
        """Add one approved skill exactly once."""
        if name not in self._allowed:
            raise ValueError(f"skill is not allowed by LoopSpec: {name}")
        self._plugins.register(_LegacySkill(name, handler))
        self._handlers[name] = handler

    async def run(self, name: str, context: Any) -> None:
        """Invoke a registered allow-listed skill."""
        try:
            handler = self._handlers[name]
        except KeyError as error:
            raise ValueError(f"skill is not registered: {name}") from error
        await handler(context)

    def names(self) -> tuple[str, ...]:
        """Return registered skills in stable LoopSpec order."""
        return tuple(name for name in self._allowed if name in self._handlers)
