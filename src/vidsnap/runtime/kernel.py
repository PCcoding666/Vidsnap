"""Bounded execution kernel that enforces policy budgets before any work."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import JsonValue, ValidationError

from vidsnap.contracts import TerminalState
from vidsnap.contracts.loopspec import default_loop_spec
from vidsnap.contracts.models import StrictModel
from vidsnap.loop.events import EventStatus
from vidsnap.loop.state_machine import BudgetExceeded
from vidsnap.plugins.base import ToolExecutionContext, ToolResult
from vidsnap.plugins.registry import PluginRegistry
from vidsnap.providers.base import ProviderError, ProviderUnavailable
from vidsnap.runtime.context import RunContext
from vidsnap.tasks.base import TaskVerification

if TYPE_CHECKING:
    from vidsnap.runtime.policies import ExecutionPolicy

OutputT = TypeVar("OutputT", bound=StrictModel)
ModelT = TypeVar("ModelT")

_SENSITIVE_KEY_PARTS = ("api_key", "authorization", "credential", "password", "secret", "token")


@dataclass(slots=True)
class KernelRunResult(Generic[OutputT]):
    """Truthful terminal output from one bounded kernel invocation."""

    terminal_state: TerminalState
    run_path: Path
    output: OutputT | None = None
    failure_reason: str | None = None
    verification: TaskVerification | None = None


class HarnessKernel(Generic[OutputT, ModelT]):
    """Execute one policy against a frozen plugin registry under enforced budgets."""

    def __init__(
        self,
        *,
        policy: ExecutionPolicy[OutputT, ModelT],
        registry: PluginRegistry,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policy = policy
        self._registry = registry
        self._registry.resolve()
        self._clock = clock
        self._max_repair_rounds = default_loop_spec().max_repair_rounds
        self._repair_rounds = 0
        self._started_at: float | None = None

    async def run(self, context: RunContext[OutputT, ModelT]) -> KernelRunResult[OutputT]:
        """Drive one run to a truthful terminal state with exactly one finalization."""
        self._repair_rounds = 0
        self._started_at = self._clock()
        run_span = context.trace.start(
            "run",
            phase="run",
            payload={"policy": type(self._policy).__name__},
        )
        failure_reason: str | None = None
        terminal_state: TerminalState | None = None
        try:
            await self._policy.execute(context, self)
        except asyncio.CancelledError:
            terminal_state = TerminalState.FAILED
            failure_reason = "cancelled"
        except BudgetExceeded as exc:
            terminal_state = TerminalState.EXHAUSTED
            failure_reason = str(exc)
        except ProviderUnavailable:
            terminal_state = TerminalState.BLOCKED
            failure_reason = "provider unavailable"
        except ProviderError:
            terminal_state = TerminalState.FAILED
            failure_reason = "provider error"
        except Exception:
            terminal_state = TerminalState.FAILED
            failure_reason = "unexpected kernel error"

        if terminal_state is None:
            terminal_state = context.terminal_state
        if terminal_state is None:
            terminal_state = TerminalState.FAILED
            failure_reason = failure_reason or "policy exited without a terminal state"
        context.terminal_state = terminal_state

        if context.output is not None and context.result_writer is not None:
            try:
                context.result_writer(context.output)
            except Exception:
                terminal_state = TerminalState.FAILED
                failure_reason = failure_reason or "result persistence failed"
                context.terminal_state = terminal_state

        self._complete_phase(
            context,
            "terminal",
            {"terminal_state": terminal_state.value, "reason": failure_reason or "completed"},
        )
        context.trace.finish(
            run_span,
            status=_trace_status(terminal_state),
            payload={"terminal_state": terminal_state.value},
        )
        context.bundle.finalize(terminal_state)
        return KernelRunResult(
            terminal_state=terminal_state,
            run_path=context.bundle.path,
            output=context.output,
            failure_reason=failure_reason,
            verification=context.verification,
        )

    async def run_probe(self, context: RunContext[OutputT, ModelT]) -> None:
        """Probe the local media once and complete the probe_media phase."""
        self._enforce_wall(context)
        span = context.trace.start("probe", phase="probe_media")
        try:
            probe = await context.media.probe(context.source.path)
        except BaseException:
            context.trace.finish(span, status="failed")
            raise
        context.probe = probe
        context.trace.finish(
            span,
            status="completed",
            payload={
                "duration_seconds": probe.duration_seconds,
                "fps": probe.fps,
                "width": probe.width,
                "height": probe.height,
                "has_audio": probe.has_audio,
            },
        )
        self._complete_phase(
            context,
            "probe_media",
            {
                "duration_seconds": probe.duration_seconds,
                "fps": probe.fps,
                "width": probe.width,
                "height": probe.height,
                "has_audio": probe.has_audio,
            },
        )

    async def run_tool(
        self,
        context: RunContext[OutputT, ModelT],
        name: str,
        arguments: Mapping[str, JsonValue] | None = None,
    ) -> ToolResult:
        """Execute one frozen, model-visible tool under strict input validation."""
        if context.probe is None:
            raise RuntimeError("probe_media must run before tool execution")
        self._enforce_wall(context)
        if context.tool_calls >= context.policy.max_tool_calls:
            raise BudgetExceeded("tool-call budget exceeded")
        plugin = self._registry.tool_by_name(name)
        try:
            validated = plugin.input_model.model_validate(dict(arguments or {}))
        except ValidationError as exc:
            raise ValueError(f"invalid arguments for tool '{name}': {exc}") from exc

        context.tool_calls += 1
        span = context.trace.start("tool.call", phase=name, payload={"name": name})
        try:
            execution = ToolExecutionContext(
                source_path=context.source.path,
                probe=context.probe,
                artifact_root=context.next_artifact_dir(),
                media=context.media,
                recognizer=context.recognizer,
                sampler=context.sampler,
                evidence_sink=context,
            )
            result = await plugin.execute(validated, execution)
        except BaseException:
            context.trace.finish(span, status="failed", payload={"name": name})
            self._emit_budget(context)
            raise
        if self._frame_count(context) > context.policy.max_evidence_frames:
            context.trace.finish(span, status="failed", payload={"name": name})
            self._emit_budget(context)
            raise BudgetExceeded("evidence-frame budget exceeded")
        context.trace.finish(span, status=result.status, payload={"name": name}, usage=result.usage)
        evidence_ids: list[JsonValue] = []
        evidence_ids.extend(result.evidence_ids)
        context.tool_result_summaries.append(
            {
                "tool": name,
                "status": result.status,
                "evidence_ids": evidence_ids,
                "summary": _redact(result.summary),
            }
        )
        self._complete_phase(context, name, {"status": result.status, **_redact(result.summary)})
        self._emit_budget(context)
        return result

    async def synthesize(self, context: RunContext[OutputT, ModelT]) -> None:
        """Run exactly one task model call over captured evidence, if any exists."""
        if context.probe is None:
            raise RuntimeError("probe_media must run before synthesis")
        if not context.evidence:
            context.terminal_state = TerminalState.NO_OP
            self._complete_phase(context, "synthesize_result", {"status": "skipped"})
            return
        self._enforce_wall(context)
        if context.model_calls >= context.policy.max_model_calls:
            raise BudgetExceeded("model-call budget exceeded")
        context.model_calls += 1
        span = context.trace.start(
            "model.request",
            phase="synthesize_result",
            payload={"task": type(context.task_adapter).__name__},
        )
        try:
            output, usage = await context.task_adapter.request_final(
                context.task_model,
                context.evidence,
                context.probe,
            )
        except BaseException:
            context.trace.finish(span, status="failed")
            self._emit_budget(context)
            raise
        context.trace.finish(span, status="completed", usage=usage)
        context.output = output
        self._complete_phase(
            context,
            "synthesize_result",
            {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
        )
        self._emit_budget(context)

    def verify(self, context: RunContext[OutputT, ModelT]) -> TaskVerification:
        """Deterministically check the synthesized output and complete the phase."""
        if context.probe is None or context.output is None:
            raise RuntimeError("verification requires a probe and a synthesized output")
        verification = context.task_adapter.verify(context.output, context.evidence, context.probe)
        context.verification = verification
        failed_gates: list[JsonValue] = []
        failed_gates.extend(gate for gate, passed in verification.gates.items() if not passed)
        context.bundle.append_event(
            "verify_claims",
            {"passed": verification.passed, "failed_gates": failed_gates},
            event_id=uuid.uuid4().hex,
            event_type="verifier.completed",
            status="completed",
        )
        self._complete_phase(
            context,
            "verify_claims",
            {"passed": verification.passed, "failed_gates": failed_gates},
        )
        return verification

    def record_iteration(self, context: RunContext[OutputT, ModelT]) -> None:
        """Record one acquisition iteration or exhaust before exceeding its budget."""
        self._enforce_wall(context)
        if context.iterations >= context.policy.max_iterations:
            raise BudgetExceeded("iteration budget exceeded")
        context.iterations += 1
        self._emit_budget(context)

    def ensure_frame_headroom(self, context: RunContext[OutputT, ModelT]) -> None:
        """Refuse further frame acquisition once the evidence-frame cap is reached."""
        self._enforce_wall(context)
        if self._frame_count(context) >= context.policy.max_evidence_frames:
            raise BudgetExceeded("evidence-frame budget exceeded")

    def remaining_frame_budget(self, context: RunContext[OutputT, ModelT]) -> int:
        """Return how many more evidence frames this run may retain."""
        return max(0, context.policy.max_evidence_frames - self._frame_count(context))

    def repair_available(self, context: RunContext[OutputT, ModelT]) -> bool:
        """Report whether one more bounded repair round is permitted."""
        return (
            self._repair_rounds < self._max_repair_rounds
            and context.iterations < context.policy.max_iterations
        )

    def record_repair(self, context: RunContext[OutputT, ModelT]) -> None:
        """Consume one repair round before a targeted re-acquisition."""
        self._enforce_wall(context)
        self._repair_rounds += 1

    def _emit_budget(self, context: RunContext[OutputT, ModelT]) -> None:
        """Append one numeric budget.updated snapshot after a counter changed."""
        context.bundle.append_event(
            "budget",
            {
                "iterations": context.iterations,
                "tool_calls": context.tool_calls,
                "model_calls": context.model_calls,
                "evidence_frames": self._frame_count(context),
            },
            event_id=uuid.uuid4().hex,
            event_type="budget.updated",
            status="completed",
        )

    def _complete_phase(
        self,
        context: RunContext[OutputT, ModelT],
        phase: str,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> None:
        context.bundle.append_event(
            phase,
            dict(payload or {}),
            event_id=uuid.uuid4().hex,
            event_type="phase.completed",
            status="completed",
        )

    def _enforce_wall(self, context: RunContext[OutputT, ModelT]) -> None:
        if self._started_at is None:
            raise RuntimeError("kernel budgets are only enforced inside run()")
        if self._clock() - self._started_at > context.policy.max_wall_seconds:
            raise BudgetExceeded("wall-clock budget exceeded")

    @staticmethod
    def _frame_count(context: RunContext[OutputT, ModelT]) -> int:
        return sum(1 for item in context.evidence if item.modality == "frame")


def _trace_status(terminal_state: TerminalState) -> EventStatus:
    if terminal_state is TerminalState.BLOCKED:
        return "blocked"
    if terminal_state in (TerminalState.EXHAUSTED, TerminalState.FAILED):
        return "failed"
    return "completed"


def _redact(payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        key: (
            "***REDACTED***"
            if any(part in key.lower() for part in _SENSITIVE_KEY_PARTS)
            else _redact_value(value)
        )
        for key, value in payload.items()
    }


def _redact_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value
