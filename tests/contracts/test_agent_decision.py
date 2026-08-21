"""Strict agent-decision contracts for the multi-step harness loop."""

import pytest
from pydantic import ValidationError

from vidsnap.contracts.agent import AgentDecision, ProviderUsage, ToolCallRequest


def test_agent_decision_requires_exactly_one_branch() -> None:
    with pytest.raises(ValidationError):
        AgentDecision(kind="tool_calls", calls=(), output=None)
    with pytest.raises(ValidationError):
        AgentDecision(kind="final", calls=(ToolCallRequest(name="x"),), output={"x": 1})
    with pytest.raises(ValidationError):
        AgentDecision(kind="tool_calls", calls=(ToolCallRequest(name="x"),), output={"x": 1})
    with pytest.raises(ValidationError):
        AgentDecision(kind="final", calls=(), output=None)


def test_agent_decision_allows_at_most_two_calls_and_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AgentDecision.model_validate(
            {
                "kind": "tool_calls",
                "calls": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            }
        )
    with pytest.raises(ValidationError):
        AgentDecision.model_validate({"kind": "final", "output": {}, "model": "other"})


def test_agent_decision_accepts_both_valid_branches() -> None:
    tool_decision = AgentDecision(
        kind="tool_calls",
        calls=(
            ToolCallRequest(name="transcribe_audio"),
            ToolCallRequest(name="sample_evidence", arguments={"max_frames": 4}),
        ),
    )
    assert tool_decision.calls[1].arguments == {"max_frames": 4}
    assert tool_decision.output is None

    final_decision = AgentDecision(kind="final", output={"summary": "done"})
    assert final_decision.calls == ()
    assert final_decision.output == {"summary": "done"}


def test_tool_call_request_names_are_bounded_and_snake_case() -> None:
    with pytest.raises(ValidationError):
        ToolCallRequest(name="")
    with pytest.raises(ValidationError):
        ToolCallRequest(name="Open-URL")
    with pytest.raises(ValidationError):
        ToolCallRequest(name="x" * 129)
    assert ToolCallRequest(name="sample_evidence").arguments == {}


def test_provider_usage_defaults_to_reported_and_accepts_counters() -> None:
    usage = ProviderUsage()
    assert usage.reported is True
    assert usage.input_bytes == 0
    missing = ProviderUsage(input_tokens=7, output_tokens=3, reported=False)
    assert missing.input_tokens == 7
    assert missing.reported is False
    with pytest.raises(ValidationError):
        ProviderUsage(input_tokens=-1)
