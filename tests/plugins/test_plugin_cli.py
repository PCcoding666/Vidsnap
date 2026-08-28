"""RED CLI tests: plugin validate/test commands with static, redacted behavior."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pytest
from pydantic import Field
from typer.testing import CliRunner

from vidsnap.cli import app
from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.base import Plugin, ToolResult
from vidsnap.plugins.manifest import PluginManifest

_VALID_CONTRACT = {
    "api_version": "vidsnap.plugin-project/v1",
    "id": "sample-tool",
    "name": "Sample Tool",
    "version": "0.1.0",
    "kind": "tool",
    "capabilities": {"provides": ["sample_tool"], "requires": []},
    "input_schema": {
        "type": "object",
        "properties": {"video_path": {"type": "string"}},
        "required": ["video_path"],
        "additionalProperties": False,
    },
    "output_schema": {"$ref": "vidsnap://schemas/tool-result/v1"},
    "permissions": ["read_media_metadata"],
    "budget_impact": {
        "model_calls": 0,
        "provider_calls": 0,
        "tool_calls": 1,
        "evidence_frames": 0,
    },
    "entry_point": "sample-tool",
}


def _write_plugin_project(root: Path, contract: dict[str, object] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    payload = dict(_VALID_CONTRACT if contract is None else contract)
    (root / "vidsnap.plugin.json").write_text(
        json.dumps(payload, ensure_ascii=True), encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        '[project.entry-points."vidsnap.plugins"]\nsample-tool = "sample_tool.plugin:TOOL"\n',
        encoding="utf-8",
    )
    return root


class _FakeToolInput(StrictModel):
    video_path: str


class _EmptyToolInput(StrictModel):
    pass


class _FakeToolPlugin:
    def __init__(
        self,
        execute_calls: list[object],
        input_model: type[StrictModel] = _FakeToolInput,
    ) -> None:
        self.manifest = PluginManifest(
            id="sample-tool",
            version="0.1.0",
            kind="tool",
            provides=("sample_tool",),
            requires=(),
            model_visible=True,
        )
        self.name = "sample_tool"
        self.input_model = input_model
        self._execute_calls = execute_calls

    async def execute(self, arguments: StrictModel, context: object) -> ToolResult:
        self._execute_calls.append(arguments)
        raise AssertionError("plugin test must never execute the tool")


def test_plugin_help_lists_validate_and_test() -> None:
    result = CliRunner().invoke(app, ["plugin", "--help"])

    assert result.exit_code == 0
    assert "validate" in result.stdout
    assert "test" in result.stdout


def test_validate_returns_valid_json_without_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_plugin_project(tmp_path / "plugin")

    def _forbidden(allowed_ids: Iterable[str]) -> tuple[Plugin, ...]:
        raise AssertionError("static validate must never call plugin discovery")

    monkeypatch.setattr("vidsnap.plugins.discovery.discover_allowed_plugins", _forbidden)

    result = CliRunner().invoke(app, ["plugin", "validate", str(root)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "VALID"


def test_test_command_returns_pass_without_executing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_plugin_project(tmp_path / "plugin")
    execute_calls: list[object] = []
    plugin = _FakeToolPlugin(execute_calls)
    discovery_calls: list[tuple[str, ...]] = []

    def _fake_discovery(allowed_ids: Iterable[str]) -> tuple[Plugin, ...]:
        discovery_calls.append(tuple(allowed_ids))
        return (plugin,)

    monkeypatch.setattr("vidsnap.plugins.discovery.discover_allowed_plugins", _fake_discovery)

    result = CliRunner().invoke(app, ["plugin", "test", str(root)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert discovery_calls == [("sample-tool",)]
    assert execute_calls == []


def test_test_command_accepts_empty_input_model_with_empty_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_plugin_project(
        tmp_path / "empty-input",
        contract={
            **_VALID_CONTRACT,
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    )
    execute_calls: list[object] = []
    plugin = _FakeToolPlugin(execute_calls, input_model=_EmptyToolInput)
    discovery_calls: list[tuple[str, ...]] = []

    def _fake_discovery(allowed_ids: Iterable[str]) -> tuple[Plugin, ...]:
        discovery_calls.append(tuple(allowed_ids))
        return (plugin,)

    monkeypatch.setattr("vidsnap.plugins.discovery.discover_allowed_plugins", _fake_discovery)

    result = CliRunner().invoke(app, ["plugin", "test", str(root)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert discovery_calls == [("sample-tool",)]
    assert execute_calls == []


@pytest.mark.parametrize("mode", ["invalid", "mismatched"])
def test_plugin_cli_reports_redacted_error_json_with_exit_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    marker = "DO-NOT-ECHO-PLUGIN-42"
    if mode == "invalid":
        root = _write_plugin_project(
            tmp_path / "invalid", contract={**_VALID_CONTRACT, "id": f"bad id {marker}"}
        )
        argv = ["plugin", "validate", str(root)]
    else:
        root = _write_plugin_project(tmp_path / "mismatched")

        def _mismatched(allowed_ids: Iterable[str]) -> tuple[Plugin, ...]:
            raise ValueError(f"{marker}: manifest id does not match entry point")

        monkeypatch.setattr("vidsnap.plugins.discovery.discover_allowed_plugins", _mismatched)
        argv = ["plugin", "test", str(root)]

    result = CliRunner().invoke(app, argv)

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert marker not in result.stdout


_MISMATCH_MARKER = "DO-NOT-ECHO-PLUGIN-43"


class _MismatchedSchemaInput(StrictModel):
    """Input whose JSON schema semantically diverges from the registered contract."""

    audio_path: str = Field(description=f"credential payload {_MISMATCH_MARKER}")
    video_path: str


class _MismatchedSchemaPlugin:
    def __init__(self, execute_calls: list[object]) -> None:
        self.manifest = PluginManifest(
            id="sample-tool",
            version="0.1.0",
            kind="tool",
            provides=("sample_tool",),
            requires=(),
            model_visible=True,
        )
        self.name = "sample_tool"
        self.input_model = _MismatchedSchemaInput
        self._execute_calls = execute_calls

    async def execute(self, arguments: StrictModel, context: object) -> ToolResult:
        self._execute_calls.append(arguments)
        raise AssertionError("plugin test must never execute the tool")


def test_test_command_reports_redacted_error_on_input_schema_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_plugin_project(tmp_path / "schema-mismatch")
    execute_calls: list[object] = []
    plugin = _MismatchedSchemaPlugin(execute_calls)
    discovery_calls: list[tuple[str, ...]] = []

    def _fake_discovery(allowed_ids: Iterable[str]) -> tuple[Plugin, ...]:
        discovery_calls.append(tuple(allowed_ids))
        return (plugin,)

    monkeypatch.setattr("vidsnap.plugins.discovery.discover_allowed_plugins", _fake_discovery)

    result = CliRunner().invoke(app, ["plugin", "test", str(root)])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert _MISMATCH_MARKER not in result.stdout
    assert discovery_calls == [("sample-tool",)]
    assert execute_calls == []
