"""Deterministic state transitions and hard resource limits for a run."""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum

from vidsnap.contracts import HarnessPolicy, TerminalState


class LoopState(str, Enum):
    """The only non-terminal stages of the evidence-grounded loop."""

    PROBE = "probe"
    PLAN = "plan"
    GATHER = "gather"
    UNDERSTAND = "understand"
    SYNTHESIZE = "synthesize"
    VERIFY = "verify"
    REPAIR = "repair"
    TERMINAL = "terminal"


class TransitionError(RuntimeError):
    """Raised when a caller attempts a state transition outside the LoopSpec."""


class BudgetExceeded(RuntimeError):
    """Raised after the controller truthfully ends the run as exhausted."""


_ALLOWED_TRANSITIONS: dict[LoopState, tuple[LoopState, ...]] = {
    LoopState.PROBE: (LoopState.PLAN,),
    LoopState.PLAN: (LoopState.GATHER,),
    LoopState.GATHER: (LoopState.UNDERSTAND,),
    LoopState.UNDERSTAND: (LoopState.SYNTHESIZE,),
    LoopState.SYNTHESIZE: (LoopState.VERIFY,),
    LoopState.VERIFY: (LoopState.REPAIR,),
    LoopState.REPAIR: (LoopState.GATHER,),
    LoopState.TERMINAL: (),
}


class LoopController:
    """Own the legal state graph and resource counters of one harness run."""

    def __init__(
        self,
        policy: HarnessPolicy,
        *,
        max_repair_rounds: int = 2,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 <= max_repair_rounds <= 2:
            raise ValueError("max_repair_rounds must be between 0 and 2")
        self.policy = policy
        self.state = LoopState.PROBE
        self.terminal_state: TerminalState | None = None
        self.model_calls = 0
        self.iterations = 0
        self.evidence_frames = 0
        self.repair_rounds = 0
        self._max_repair_rounds = max_repair_rounds
        self._clock = clock
        self._started_at = clock()

    @property
    def elapsed_seconds(self) -> float:
        """Return elapsed monotonic time for diagnostics and event records."""
        return self._clock() - self._started_at

    def transition(self, target: LoopState) -> None:
        """Advance only along the approved LoopSpec graph."""
        self._ensure_active()
        self._enforce_wall_clock()
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise TransitionError(f"invalid transition: {self.state.value} -> {target.value}")
        if target is LoopState.REPAIR:
            if self.repair_rounds >= self._max_repair_rounds:
                self._exhaust("repair-round budget exceeded")
            self.repair_rounds += 1
        self.state = target

    def record_iteration(self) -> None:
        """Record an iteration or end the run before exceeding its budget."""
        self._ensure_active()
        self._enforce_wall_clock()
        if self.iterations >= self.policy.max_iterations:
            self._exhaust("iteration budget exceeded")
        self.iterations += 1

    def record_model_call(self) -> None:
        """Record a model call or end the run before exceeding its budget."""
        self._ensure_active()
        self._enforce_wall_clock()
        if self.model_calls >= self.policy.max_model_calls:
            self._exhaust("model-call budget exceeded")
        self.model_calls += 1

    def record_evidence_frames(self, count: int = 1) -> None:
        """Record retained evidence frames or end the run at the frame cap."""
        self._ensure_active()
        self._enforce_wall_clock()
        if count < 1:
            raise ValueError("evidence frame count must be positive")
        if self.evidence_frames + count > self.policy.max_evidence_frames:
            self._exhaust("evidence-frame budget exceeded")
        self.evidence_frames += count

    def check_wall_clock(self) -> None:
        """Expose a cooperative wall-clock check for long-running ports."""
        self._ensure_active()
        self._enforce_wall_clock()

    def terminate(self, terminal_state: TerminalState) -> None:
        """End the run with a truthful non-budget terminal state."""
        self._ensure_active()
        self.state = LoopState.TERMINAL
        self.terminal_state = terminal_state

    def _ensure_active(self) -> None:
        if self.state is LoopState.TERMINAL:
            raise TransitionError("loop is already terminal")

    def _enforce_wall_clock(self) -> None:
        if self.elapsed_seconds > self.policy.max_wall_seconds:
            self._exhaust("wall-clock budget exceeded")

    def _exhaust(self, detail: str) -> None:
        self.state = LoopState.TERMINAL
        self.terminal_state = TerminalState.EXHAUSTED
        raise BudgetExceeded(detail)
