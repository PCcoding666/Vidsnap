"""Allow-listed executable skills used by the bounded harness loop."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from vidsnap.contracts import LoopSpec

SkillHandler = Callable[[Any], Awaitable[None]]


class SkillRegistry:
    """Register and invoke only skills named in the current LoopSpec."""

    def __init__(self, loop_spec: LoopSpec) -> None:
        self._allowed = loop_spec.allowed_skills
        self._handlers: dict[str, SkillHandler] = {}

    def register(self, name: str, handler: SkillHandler) -> None:
        """Add one approved skill exactly once."""
        if name not in self._allowed:
            raise ValueError(f"skill is not allowed by LoopSpec: {name}")
        if name in self._handlers:
            raise ValueError(f"skill is already registered: {name}")
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
