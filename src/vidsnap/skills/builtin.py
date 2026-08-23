"""Assembly helper for the six built-in, LoopSpec-approved skill handlers."""

from __future__ import annotations

from collections.abc import Mapping

from vidsnap.contracts import LoopSpec
from vidsnap.skills.base import SkillHandler, SkillRegistry


def register_builtin_skills(
    loop_spec: LoopSpec,
    handlers: Mapping[str, SkillHandler],
) -> SkillRegistry:
    """Build a complete registry and reject missing or extra built-in handlers.

    Deprecated for one release: retained for existing callers while new code
    assembles Tool Plugins through PluginRegistry instead.
    """
    if set(handlers) != set(loop_spec.allowed_skills):
        raise ValueError("built-in handlers must match the LoopSpec allow-list exactly")
    registry = SkillRegistry(loop_spec)
    for name in loop_spec.allowed_skills:
        registry.register(name, handlers[name])
    return registry
