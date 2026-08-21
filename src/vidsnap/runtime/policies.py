"""Bounded execution policies that order kernel phases without model steering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

from pydantic import JsonValue

from vidsnap.contracts import TerminalState
from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.builtin import default_tool_plugins
from vidsnap.plugins.registry import PluginRegistry
from vidsnap.runtime.context import RunContext

if TYPE_CHECKING:
    from vidsnap.runtime.kernel import HarnessKernel

OutputT = TypeVar("OutputT", bound=StrictModel)
ModelT = TypeVar("ModelT")

_MAX_TOOL_WINDOWS = 3


class ExecutionPolicy(Protocol, Generic[OutputT, ModelT]):
    """A deterministic phase sequence the kernel executes under enforced budgets."""

    async def execute(
        self,
        context: RunContext[OutputT, ModelT],
        kernel: HarnessKernel[OutputT, ModelT],
    ) -> None:
        """Drive one bounded run to a truthful terminal state on the context."""


def default_plugin_registry() -> PluginRegistry:
    """Assemble and freeze the approved default tool plugins exactly once."""
    plugins = default_tool_plugins()
    registry = PluginRegistry(allowed_ids=tuple(plugin.manifest.id for plugin in plugins))
    for plugin in plugins:
        registry.register(plugin)
    registry.resolve()
    return registry


class FixedPolicy(Generic[OutputT, ModelT]):
    """A fixed probe-to-verification sequence that never consults the agent model."""

    async def execute(
        self,
        context: RunContext[OutputT, ModelT],
        kernel: HarnessKernel[OutputT, ModelT],
    ) -> None:
        """Acquire evidence, synthesize, verify, and repair in a fixed order."""
        await kernel.run_probe(context)
        targeted_windows: tuple[tuple[float, float], ...] = ()
        repair_round = False
        while True:
            await self._gather(context, kernel, targeted_windows, repair_round=repair_round)
            await kernel.synthesize(context)
            if context.terminal_state is not None:
                return
            verification = kernel.verify(context)
            if verification.passed:
                context.terminal_state = TerminalState.SUCCEEDED
                return
            if not kernel.repair_available(context):
                context.terminal_state = TerminalState.PARTIAL
                return
            kernel.record_repair(context)
            targeted_windows = verification.targeted_windows
            repair_round = True

    async def _gather(
        self,
        context: RunContext[OutputT, ModelT],
        kernel: HarnessKernel[OutputT, ModelT],
        targeted_windows: tuple[tuple[float, float], ...],
        *,
        repair_round: bool,
    ) -> None:
        """Run one acquisition iteration; repair rounds resample frames only."""
        kernel.record_iteration(context)
        probe = context.probe
        if not repair_round and probe is not None and probe.has_audio:
            await kernel.run_tool(context, "transcribe_audio", {})
        kernel.ensure_frame_headroom(context)
        arguments: dict[str, JsonValue] = {
            "max_frames": kernel.remaining_frame_budget(context),
        }
        windows = _valid_windows(targeted_windows)
        if windows:
            arguments["windows"] = windows
        await kernel.run_tool(context, "sample_evidence", arguments)


def _valid_windows(windows: tuple[tuple[float, float], ...]) -> list[JsonValue]:
    """Keep only ordered, positive windows the sampling schema will accept."""
    valid: list[JsonValue] = []
    for start, end in windows:
        if start >= 0 and end > start:
            valid.append({"start_seconds": start, "end_seconds": end})
    return valid[:_MAX_TOOL_WINDOWS]
