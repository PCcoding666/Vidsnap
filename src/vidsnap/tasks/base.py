"""Generic task-adapter contract between the kernel and one analysis task."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar

from pydantic import JsonValue

from vidsnap.contracts import Evidence, VideoGoal
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.models import StrictModel
from vidsnap.video.probe import MediaProbe

OutputT = TypeVar("OutputT", bound=StrictModel)
ModelT = TypeVar("ModelT", contravariant=True)


class TaskVerification(StrictModel):
    """The deterministic verifier outcome one task adapter exposes to the kernel."""

    passed: bool
    gates: dict[str, bool]
    targeted_windows: tuple[tuple[float, float], ...] = ()


class TaskAdapter(Protocol, Generic[OutputT, ModelT]):
    """Typed seams for final-output requests, parsing, and verification."""

    goal: VideoGoal
    output_model: type[OutputT]

    async def request_final(
        self,
        model: ModelT,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> tuple[OutputT, ProviderUsage]:
        """Run the task's final model call and map real provider usage."""

    def parse_final(self, payload: dict[str, JsonValue]) -> OutputT:
        """Validate one strict output payload; reject unknown fields."""

    def verify(
        self,
        output: OutputT,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> TaskVerification:
        """Check one parsed output against captured evidence deterministically."""
