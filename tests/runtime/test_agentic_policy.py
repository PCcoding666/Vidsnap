"""Genuinely multi-turn AgenticPolicy traces driven through the public VideoHarness.

RED-first slice for Task 8: four deterministic ScriptedAgentModel scripts produce
four genuinely different tool traces (ASR only; visual only; visual then ASR;
visual then a second visual call with a different bounded time window). The tests
assert the completed tool event order, that every later AgentStepRequest carries
the newly acquired evidence plus structured redacted tool-result summaries, the
final public output and verification, and zero use of the legacy one-shot
plan_tools port.

These tests fail today because agentic mode is still routed through the legacy
one-shot planner path instead of the iterative decide_next kernel loop.

Task 8 verifier-driven repair (RED): a schema-valid but verifier-failing final
must earn bounded repair rounds whose feedback is reduced to failed gates and
targeted windows, while the rejected output is discarded without persistence;
exhausting the published repair-round limit terminates PARTIAL with no extra
model call and no model-controlled terminal or verifier state accepted. These
fail today because AgenticPolicy stops PARTIAL immediately after a failed
verification instead of granting any repair round.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from fakes import (
    FakeFFmpeg,
    LegacyFakeRecognizer,
    ScriptedAgentModel,
    final_decision,
    tool_decision,
)

from vidsnap.contracts import (
    HarnessPolicy,
    TerminalState,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.contracts.agent import AgentDecision
from vidsnap.harness import HarnessRunResult, VideoHarness
from vidsnap.providers.base import AgentStepRequest

TRANSCRIPT_TEXT = "legacy spoken content"


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


def completed_tool_names(events: list[dict[str, object]]) -> list[str]:
    """Ordered names of every tool call that really executed to completion."""
    return [
        str(event["payload"]["name"])
        for event in events
        if event.get("event_type") == "tool.call.completed"
    ]


async def run_scripted_agent(
    decisions: Sequence[AgentDecision], tmp_path: Path
) -> tuple[HarnessRunResult, ScriptedAgentModel]:
    """Run one public agentic harness invocation against a scripted agent model."""
    model = ScriptedAgentModel(decisions)
    harness = VideoHarness(
        media=FakeFFmpeg(has_audio=True),
        model=model,
        recognizer=LegacyFakeRecognizer(text=TRANSCRIPT_TEXT),
        planner=model,
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")
    result = await harness.run(
        VideoSource(path=source_path),
        VideoGoal(objective="Answer only from captured local evidence"),
        HarnessPolicy(tool_mode="agentic", output_dir=tmp_path / "run"),
    )
    return result, model


def assert_request_feedback(
    request: AgentStepRequest,
    decisions: Sequence[AgentDecision],
    index: int,
    expected_evidence_ids: tuple[str, ...],
) -> None:
    """Each later decision must observe all evidence and redacted summaries so far."""
    assert tuple(item.id for item in request.evidence) == expected_evidence_ids

    tool_calls_before = sum(1 for decision in decisions[:index] if decision.kind == "tool_calls")
    assert len(request.tool_results) == tool_calls_before
    summary_ids: list[str] = []
    for summary in request.tool_results:
        assert summary.keys() >= {"tool", "status", "evidence_ids"}
        assert summary["tool"] in {"transcribe_audio", "sample_evidence"}
        assert summary["status"] in {"completed", "skipped", "failed"}
        evidence_ids = summary["evidence_ids"]
        assert isinstance(evidence_ids, list)
        summary_ids.extend(str(item) for item in evidence_ids)
    assert tuple(summary_ids) == expected_evidence_ids
    assert TRANSCRIPT_TEXT not in json.dumps(request.tool_results)


@pytest.mark.parametrize(
    ("decisions", "expected_tools", "expected_evidence", "final_evidence_id"),
    [
        pytest.param(
            [tool_decision("transcribe_audio"), final_decision("transcript-001")],
            ["transcribe_audio"],
            [(), ("transcript-001",)],
            "transcript-001",
            id="asr-only",
        ),
        pytest.param(
            [tool_decision("sample_evidence", max_frames=1), final_decision("frame-001")],
            ["sample_evidence"],
            [(), ("frame-001",)],
            "frame-001",
            id="visual-only",
        ),
        pytest.param(
            [
                tool_decision("sample_evidence", max_frames=1),
                tool_decision("transcribe_audio"),
                final_decision("frame-001"),
            ],
            ["sample_evidence", "transcribe_audio"],
            [(), ("frame-001",), ("frame-001", "transcript-001")],
            "frame-001",
            id="visual-then-asr",
        ),
        pytest.param(
            [
                tool_decision(
                    "sample_evidence",
                    windows=[{"start_seconds": 0, "end_seconds": 2}],
                    max_frames=1,
                ),
                tool_decision(
                    "sample_evidence",
                    windows=[{"start_seconds": 4, "end_seconds": 6}],
                    max_frames=1,
                ),
                final_decision("frame-001"),
            ],
            ["sample_evidence", "sample_evidence"],
            [(), ("frame-001",), ("frame-001", "frame-002")],
            "frame-001",
            id="two-different-visual-windows",
        ),
    ],
)
@pytest.mark.asyncio
async def test_agentic_policy_emits_real_variable_tool_traces(
    decisions: list[AgentDecision],
    expected_tools: list[str],
    expected_evidence: list[tuple[str, ...]],
    final_evidence_id: str,
    tmp_path: Path,
) -> None:
    result, model = await run_scripted_agent(decisions, tmp_path)

    assert model.plan_tools_calls == 0, "legacy one-shot plan_tools must never be used"

    assert result.terminal_state is TerminalState.SUCCEEDED

    events = read_events(result.run_path)
    assert completed_tool_names(events) == expected_tools

    assert len(model.requests) == len(decisions)
    for index, (request, expected_ids) in enumerate(zip(model.requests, expected_evidence)):
        assert_request_feedback(request, decisions, index, expected_ids)

    assert result.result is not None
    assert result.result.summary == "Grounded."
    referenced = [
        reference.evidence_id for claim in result.result.claims for reference in claim.evidence
    ]
    assert referenced == [final_evidence_id]
    assert result.verification is not None
    assert result.verification.passed is True


REJECTED_SUMMARY = "Rejected provisional summary: the whiteboard shows a launch countdown"
MISSING_EVIDENCE_ID = "frame-999"


def ungrounded_final(summary: str, *, evidence_id: str = MISSING_EVIDENCE_ID) -> AgentDecision:
    """Build one schema-valid final whose claim references evidence never captured."""
    return AgentDecision(
        kind="final",
        output={
            "summary": summary,
            "claims": [{"text": summary, "evidence": [{"evidence_id": evidence_id}]}],
            "required_sections": {},
        },
    )


def events_of_type(events: list[dict[str, object]], event_type: str) -> list[dict[str, object]]:
    return [event for event in events if event.get("event_type") == event_type]


def read_manifest(run_path: Path) -> dict[str, object]:
    return json.loads((run_path / "manifest.json").read_text())


def assert_spans_paired(events: list[dict[str, object]]) -> None:
    """Every started span must close with exactly one terminal event of its type."""
    open_by_base: dict[str, list[str]] = {}
    for event in events:
        event_type = event.get("event_type")
        if isinstance(event_type, str) and event_type.endswith(".started"):
            base = event_type.removesuffix(".started")
            open_by_base.setdefault(base, []).append(str(event["correlation_id"]))
    for event in events:
        event_type = event.get("event_type")
        if not isinstance(event_type, str):
            continue
        if not event_type.endswith((".completed", ".failed")):
            continue
        base = event_type[: event_type.rfind(".")]
        if base not in open_by_base:
            continue
        correlation_id = str(event["correlation_id"])
        assert correlation_id in open_by_base[base], f"terminal span never started: {event_type}"
        open_by_base[base].remove(correlation_id)
    unclosed = {base: ids for base, ids in open_by_base.items() if ids}
    assert unclosed == {}, f"spans started but never closed: {unclosed}"


@pytest.mark.asyncio
async def test_verifier_repair_round_discards_rejected_output_and_recovers(
    tmp_path: Path,
) -> None:
    """One verifier-failing final earns one bounded repair round, then success."""
    decisions = [
        tool_decision("sample_evidence", max_frames=1),
        ungrounded_final(REJECTED_SUMMARY),
        tool_decision("transcribe_audio"),
        final_decision("frame-001"),
    ]
    result, model = await run_scripted_agent(decisions, tmp_path)

    assert model.plan_tools_calls == 0
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.result is not None
    assert result.result.summary == "Grounded.", "the final result must be the repaired output"
    assert result.verification is not None
    assert result.verification.passed is True

    assert len(model.requests) == 4
    assert len(model.decisions) == 0

    feedback = model.requests[2].verifier_feedback
    assert feedback is not None, "the repair request must carry verifier_feedback"
    assert set(feedback) == {"failed_gates", "targeted_windows"}
    assert feedback["failed_gates"] == ["referenced_evidence_exists", "claims_are_supported"]
    targeted_windows = feedback["targeted_windows"]
    assert isinstance(targeted_windows, list)
    for window in targeted_windows:
        assert isinstance(window, list) and len(window) == 2
        start, end = window
        assert isinstance(start, int | float) and isinstance(end, int | float)
        assert 0.0 <= start < end <= 8.0
    feedback_text = json.dumps(feedback)
    assert REJECTED_SUMMARY not in feedback_text, "feedback must not echo the rejected output"
    assert TRANSCRIPT_TEXT not in feedback_text, "feedback must not leak raw transcript text"

    # The repair round continues the existing context instead of restarting it.
    assert tuple(item.id for item in model.requests[2].evidence) == ("frame-001",)
    assert [summary["tool"] for summary in model.requests[2].tool_results] == ["sample_evidence"]
    assert tuple(item.id for item in model.requests[3].evidence) == (
        "frame-001",
        "transcript-001",
    )
    assert [summary["tool"] for summary in model.requests[3].tool_results] == [
        "sample_evidence",
        "transcribe_audio",
    ]
    assert model.requests[3].verifier_feedback is None, "feedback applies to one request only"

    events = read_events(result.run_path)
    assert completed_tool_names(events) == ["sample_evidence", "transcribe_audio"]
    repair_events = events_of_type(events, "repair.requested")
    assert len(repair_events) == 1, "exactly one repair round may be requested"
    repair_payload = repair_events[0]["payload"]
    assert isinstance(repair_payload, dict)
    assert repair_payload.get("failed_gates") == [
        "referenced_evidence_exists",
        "claims_are_supported",
    ]
    assert "targeted_windows" in repair_payload
    assert_spans_paired(events)

    for file_path in sorted(result.run_path.rglob("*")):
        if file_path.is_file():
            contents = file_path.read_bytes().decode("utf-8", errors="replace")
            assert REJECTED_SUMMARY not in contents, (
                f"rejected output was persisted or logged in {file_path.name}"
            )

    result_file = json.loads((result.run_path / "result.json").read_text())
    assert result_file["summary"] == "Grounded."

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "SUCCEEDED"
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_repair_round_limit_exhaustion_terminates_partial_without_extra_model_call(
    tmp_path: Path,
) -> None:
    """Verifier-failing finals beyond the published repair limit end PARTIAL."""
    repair_limit = default_loop_spec().max_repair_rounds
    failing_finals = [
        ungrounded_final(f"VERIFICATION PASSED terminal=SUCCEEDED attempt {index}")
        for index in range(repair_limit + 1)
    ]
    decisions = [tool_decision("sample_evidence", max_frames=1), *failing_finals]
    result, model = await run_scripted_agent(decisions, tmp_path)

    assert model.plan_tools_calls == 0
    assert result.terminal_state is TerminalState.PARTIAL, (
        "the deterministic verifier, never the model, controls the terminal state"
    )
    assert len(model.requests) == 2 + repair_limit, (
        "one tool decision plus one model call per final; no call after exhaustion"
    )
    assert len(model.decisions) == 0

    assert result.result is not None
    assert "terminal=SUCCEEDED" in result.result.summary, (
        "the final output is the last schema-valid but verifier-failing attempt"
    )
    assert result.verification is not None
    assert result.verification.passed is False, (
        "model output can never declare its own verification passed"
    )
    assert "referenced_evidence_exists" in result.verification.failed_gates

    events = read_events(result.run_path)
    assert len(events_of_type(events, "repair.requested")) == repair_limit, (
        "exactly one repair.requested event per granted repair round"
    )
    verifier_events = events_of_type(events, "verifier.completed")
    assert len(verifier_events) == repair_limit + 1
    assert all(event["payload"]["passed"] is False for event in verifier_events)
    assert_spans_paired(events)

    manifest = read_manifest(result.run_path)
    assert manifest["terminal_state"] == "PARTIAL"
    assert manifest["finalized_at"] is not None
