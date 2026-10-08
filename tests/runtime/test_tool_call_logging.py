"""tool.call events record redacted validated arguments and the call fingerprint.

The kernel already validates every tool call and computes a canonical call
fingerprint to reject duplicates; these tests require both to be written to the
``tool.call.started`` payload so a finished RunBundle shows exactly what each
tool was asked to do, while sensitive argument values never reach the ledger.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fakes import ScriptedAgentModel, final_decision, tool_decision
from pydantic import Field
from test_fixed_policy import build_context, make_kernel, read_events

from vidsnap.contracts import TerminalState
from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.base import ToolExecutionContext, ToolResult
from vidsnap.plugins.manifest import PluginManifest
from vidsnap.plugins.registry import PluginRegistry
from vidsnap.runtime import AgenticPolicy, HarnessKernel, RunContext, default_plugin_registry

_SENSITIVE_VALUE = "sentinel-tool-argument-value-5c1d"


def _expected_fingerprint(name: str, arguments: dict[str, object]) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{name}\x1f{canonical}".encode()).hexdigest()


def _started_tool_payloads(run_path: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for event in read_events(run_path):
        if event.get("event_type") == "tool.call.started":
            payload = event["payload"]
            assert isinstance(payload, dict)
            payloads.append(payload)
    return payloads


@pytest.mark.asyncio
async def test_fixed_run_records_validated_arguments_and_fingerprint(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)

    await make_kernel().run(context)

    payloads = _started_tool_payloads(context.bundle.path)
    assert [payload["name"] for payload in payloads] == ["transcribe_audio", "sample_evidence"]
    transcribe, sample = payloads
    # Validated arguments include schema defaults, exactly as the tool received them.
    assert transcribe["arguments"] == {"windows": []}
    assert sample["arguments"] == {"windows": [], "max_frames": 96}
    assert transcribe["fingerprint"] == _expected_fingerprint("transcribe_audio", {"windows": []})
    assert sample["fingerprint"] == _expected_fingerprint(
        "sample_evidence", {"windows": [], "max_frames": 96}
    )


@pytest.mark.asyncio
async def test_agentic_run_records_model_requested_arguments(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    agent = ScriptedAgentModel(
        [
            tool_decision(
                "sample_evidence",
                max_frames=2,
                windows=[{"start_seconds": 0.5, "end_seconds": 4.0}],
            ),
            final_decision("frame-001"),
        ]
    )
    context.agent_model = agent
    kernel = HarnessKernel(policy=AgenticPolicy(), registry=default_plugin_registry())

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.SUCCEEDED
    (payload,) = _started_tool_payloads(context.bundle.path)
    expected_arguments = {
        "windows": [{"start_seconds": 0.5, "end_seconds": 4.0}],
        "max_frames": 2,
    }
    assert payload == {
        "name": "sample_evidence",
        "arguments": expected_arguments,
        "fingerprint": _expected_fingerprint("sample_evidence", expected_arguments),
    }


class _SensitiveArgs(StrictModel):
    api_key: str = Field(min_length=1)
    count: int = 1


class _SensitiveArgumentTool:
    manifest = PluginManifest(
        id="tests.tool.sensitive_arguments",
        version="1.0.0",
        kind="tool",
        model_visible=True,
    )
    name: str = "sensitive_arguments"
    input_model: type[StrictModel] = _SensitiveArgs

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        return ToolResult(status="completed")


class _OneSensitiveCallPolicy:
    async def execute(self, context: RunContext, kernel: HarnessKernel) -> None:
        await kernel.run_probe(context)
        await kernel.run_tool(
            context, "sensitive_arguments", {"api_key": _SENSITIVE_VALUE, "count": 2}
        )
        context.terminal_state = TerminalState.NO_OP


@pytest.mark.asyncio
async def test_sensitive_argument_values_are_redacted_but_fingerprinted(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=False)
    tool = _SensitiveArgumentTool()
    registry = PluginRegistry(allowed_ids=[tool.manifest.id])
    registry.register(tool)
    kernel = HarnessKernel(policy=_OneSensitiveCallPolicy(), registry=registry)

    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.NO_OP
    (payload,) = _started_tool_payloads(context.bundle.path)
    assert payload["arguments"] == {"api_key": "***REDACTED***", "count": 2}
    # The fingerprint is the one-way digest the kernel uses for duplicate rejection.
    assert payload["fingerprint"] == _expected_fingerprint(
        "sensitive_arguments", {"api_key": _SENSITIVE_VALUE, "count": 2}
    )
    ledger = (context.bundle.path / "events.jsonl").read_text(encoding="utf-8")
    assert _SENSITIVE_VALUE not in ledger


@pytest.mark.asyncio
async def test_tool_terminal_payloads_keep_their_v010_shape(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)

    await make_kernel().run(context)

    completed = [
        event["payload"]
        for event in read_events(context.bundle.path)
        if event.get("event_type") == "tool.call.completed"
    ]
    assert completed == [{"name": "transcribe_audio"}, {"name": "sample_evidence"}]
