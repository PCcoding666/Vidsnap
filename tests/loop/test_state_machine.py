"""Bounded loop-state and resource-budget behavior."""

import pytest

from vidsnap.contracts import HarnessPolicy, TerminalState
from vidsnap.loop.state_machine import BudgetExceeded, LoopController, LoopState, TransitionError


def test_model_call_budget_terminates_without_success() -> None:
    controller = LoopController(HarnessPolicy(max_model_calls=1))

    controller.record_model_call()

    with pytest.raises(BudgetExceeded):
        controller.record_model_call()

    assert controller.terminal_state is TerminalState.EXHAUSTED
    assert controller.state is LoopState.TERMINAL


def test_controller_only_permits_the_approved_state_path() -> None:
    controller = LoopController(HarnessPolicy())

    with pytest.raises(TransitionError):
        controller.transition(LoopState.GATHER)

    controller.transition(LoopState.PLAN)
    controller.transition(LoopState.GATHER)
    controller.transition(LoopState.UNDERSTAND)
    controller.transition(LoopState.SYNTHESIZE)
    controller.transition(LoopState.VERIFY)
    controller.transition(LoopState.REPAIR)
    controller.transition(LoopState.GATHER)

    assert controller.state is LoopState.GATHER


def test_iteration_budget_exhaustion_cannot_report_success() -> None:
    controller = LoopController(HarnessPolicy(max_iterations=1))
    controller.record_iteration()

    with pytest.raises(BudgetExceeded):
        controller.record_iteration()

    assert controller.terminal_state is TerminalState.EXHAUSTED


def test_frame_and_wall_clock_budgets_also_end_as_exhausted() -> None:
    frame_limited = LoopController(HarnessPolicy(max_evidence_frames=1))
    frame_limited.record_evidence_frames()
    with pytest.raises(BudgetExceeded):
        frame_limited.record_evidence_frames()
    assert frame_limited.terminal_state is TerminalState.EXHAUSTED

    clock = [0.0]
    time_limited = LoopController(HarnessPolicy(max_wall_seconds=1), clock=lambda: clock[0])
    clock[0] = 1.1
    with pytest.raises(BudgetExceeded):
        time_limited.check_wall_clock()
    assert time_limited.terminal_state is TerminalState.EXHAUSTED
