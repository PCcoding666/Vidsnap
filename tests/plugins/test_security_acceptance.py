"""Security acceptance behaviors for the plugin manifest and registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.base import ToolExecutionContext, ToolResult
from vidsnap.plugins.manifest import PluginManifest
from vidsnap.plugins.registry import PluginRegistry


class ValidToolPlugin:
    def __init__(self, plugin_id: str, *, model_visible: bool) -> None:
        self.name = plugin_id.rsplit(".", 1)[-1]
        self.manifest = PluginManifest(
            id=plugin_id,
            version="1.0.0",
            kind="tool",
            model_visible=model_visible,
        )
        self.input_model: type[StrictModel] = StrictModel

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        return ToolResult(status="completed")


class BrokenToolPlugin:
    """Declares kind=tool in its manifest but does not satisfy ToolPlugin."""

    def __init__(self, plugin_id: str) -> None:
        self.manifest = PluginManifest(id=plugin_id, version="1.0.0", kind="tool")


@pytest.mark.parametrize("kind", ["policy", "task", "observer"])
def test_manifest_rejects_model_visible_for_non_tool_kinds(kind: str) -> None:
    with pytest.raises(ValidationError, match="model_visible"):
        PluginManifest(id="vidsnap.x", version="1.0.0", kind=kind, model_visible=True)

    manifest = PluginManifest(id="vidsnap.x", version="1.0.0", kind=kind)
    assert manifest.model_visible is False


def test_manifest_allows_model_visible_for_tool_kind() -> None:
    manifest = PluginManifest(id="vidsnap.x", version="1.0.0", kind="tool", model_visible=True)
    assert manifest.model_visible is True


def test_resolve_rejects_tool_kind_plugin_not_satisfying_tool_protocol() -> None:
    registry = PluginRegistry(allowed_ids={"broken"})
    registry.register(BrokenToolPlugin("broken"))
    with pytest.raises(ValueError, match="broken"):
        registry.resolve()


def test_resolve_rejects_broken_tool_even_with_valid_siblings() -> None:
    registry = PluginRegistry(allowed_ids={"broken", "ok"})
    registry.register(ValidToolPlugin("ok", model_visible=True))
    registry.register(BrokenToolPlugin("broken"))
    with pytest.raises(ValueError, match="broken"):
        registry.resolve()


def test_tool_by_name_never_returns_hidden_tools() -> None:
    registry = PluginRegistry(allowed_ids={"hidden", "visible"})
    registry.register(ValidToolPlugin("hidden", model_visible=False))
    registry.register(ValidToolPlugin("visible", model_visible=True))

    resolved = registry.resolve()
    assert [plugin.manifest.id for plugin in resolved] == ["hidden", "visible"]

    assert registry.tool_by_name("visible").name == "visible"
    with pytest.raises(ValueError, match="no registered tool"):
        registry.tool_by_name("hidden")
