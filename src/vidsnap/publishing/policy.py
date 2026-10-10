"""Fixed publishing policy: probe, one bounded sample call, synthesize, verify."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, TypeVar

from vidsnap.contracts import TerminalState
from vidsnap.contracts.models import StrictModel

if TYPE_CHECKING:
    from vidsnap.runtime.context import RunContext
    from vidsnap.runtime.kernel import HarnessKernel

OutputT = TypeVar("OutputT", bound=StrictModel)
ModelT = TypeVar("ModelT")

_SAMPLE_MAX_FRAMES = 12


class PublishingPolicy(Generic[OutputT, ModelT]):
    """Probe once, sample a fixed frame budget, synthesize once, and verify once."""

    async def execute(
        self,
        context: RunContext[OutputT, ModelT],
        kernel: HarnessKernel[OutputT, ModelT],
    ) -> None:
        """Drive one bounded publishing run without tools beyond sample_evidence."""
        await kernel.run_probe(context)
        await kernel.run_tool(context, "sample_evidence", {"max_frames": _SAMPLE_MAX_FRAMES})
        await kernel.synthesize(context)
        if context.terminal_state is not None:
            return
        verification = kernel.verify(context)
        if verification.passed:
            context.terminal_state = TerminalState.SUCCEEDED
        else:
            context.terminal_state = TerminalState.PARTIAL
