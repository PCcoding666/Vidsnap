"""A run's ``allowed_tools`` can only narrow the default tool set, and FixedPolicy obeys it."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_fixed_policy import build_context, read_events

from vidsnap.contracts import HarnessPolicy, TerminalState
from vidsnap.runtime import FixedPolicy, HarnessKernel, default_plugin_registry


def _tool_phases(run_path: Path) -> list[object]:
    return [
        event["phase"]
        for event in read_events(run_path)
        if event.get("event_type") == "tool.call.started"
    ]


def test_registry_subset_never_adds_a_tool() -> None:
    assert [p.name for p in default_plugin_registry(("sample_evidence",)).resolve()] == [
        "sample_evidence"
    ]
    assert default_plugin_registry(("run_shell",)).resolve() == ()
    names = {p.name for p in default_plugin_registry().resolve()}
    assert names == {"transcribe_audio", "sample_evidence"}


@pytest.mark.asyncio
async def test_fixed_policy_skips_tools_the_run_did_not_allow(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.policy = HarnessPolicy(allowed_tools=("sample_evidence",))
    kernel = HarnessKernel(
        policy=FixedPolicy(), registry=default_plugin_registry(context.policy.allowed_tools)
    )

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert _tool_phases(context.bundle.path) == ["sample_evidence"]
    assert not kernel.has_tool("transcribe_audio")
    assert kernel.has_tool("sample_evidence")


@pytest.mark.asyncio
async def test_no_allowed_tools_ends_as_no_op(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.policy = HarnessPolicy(allowed_tools=())
    kernel = HarnessKernel(policy=FixedPolicy(), registry=default_plugin_registry(()))

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.NO_OP
    assert _tool_phases(context.bundle.path) == []
