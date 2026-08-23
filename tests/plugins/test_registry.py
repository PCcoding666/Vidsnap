"""Plugin manifest, registry, and allow-listed discovery behavior."""

from __future__ import annotations

import dataclasses
import importlib.metadata
from typing import Any

import pytest
from pydantic import ValidationError

from vidsnap.contracts.models import StrictModel
from vidsnap.plugins.base import ToolExecutionContext, ToolResult
from vidsnap.plugins.discovery import discover_allowed_plugins
from vidsnap.plugins.manifest import PluginManifest
from vidsnap.plugins.registry import PluginRegistry


class FakePlugin:
    def __init__(
        self,
        plugin_id: str,
        *,
        provides: tuple[str, ...] = (),
        requires: tuple[str, ...] = (),
    ) -> None:
        self.name = plugin_id.rsplit(".", 1)[-1]
        self.manifest = PluginManifest(
            id=plugin_id,
            version="1.0.0",
            kind="tool",
            provides=provides,
            requires=requires,
            model_visible=True,
        )
        self.input_model: type[StrictModel] = StrictModel

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        del arguments, context
        return ToolResult(status="completed")


class ManifestOnlyPlugin:
    def __init__(
        self,
        plugin_id: str,
        *,
        kind: str = "policy",
        provides: tuple[str, ...] = (),
        requires: tuple[str, ...] = (),
    ) -> None:
        self.manifest = PluginManifest(
            id=plugin_id,
            version="1.0.0",
            kind=kind,
            provides=provides,
            requires=requires,
        )


class FakeEntryPoint:
    def __init__(self, plugin: FakePlugin, loaded: list[str]) -> None:
        self.name = plugin.manifest.id
        self._plugin = plugin
        self._loaded = loaded

    def load(self) -> Any:
        self._loaded.append(self.name)
        return lambda: self._plugin


class FakeEntryPoints(tuple):
    def select(self, *, group: str) -> FakeEntryPoints:
        assert group == "vidsnap.plugins"
        return self


def test_plugin_manifest_rejects_invalid_schema() -> None:
    with pytest.raises(ValidationError):
        PluginManifest(id="Bad ID", version="1.0.0", kind="tool")
    with pytest.raises(ValidationError):
        PluginManifest(id="ok", version="1.0", kind="tool")
    with pytest.raises(ValidationError):
        PluginManifest(id="ok", version="1.0.0", kind="widget")
    with pytest.raises(ValidationError):
        PluginManifest(api_version="other/v2", id="ok", version="1.0.0", kind="tool")

    manifest = PluginManifest(id="vidsnap.tool.sample_evidence", version="1.0.0", kind="tool")
    assert manifest.api_version == "vidsnap.plugin/v1"
    assert manifest.model_visible is False
    assert manifest.provides == ()
    assert manifest.requires == ()


def test_registry_rejects_duplicate_missing_and_cyclic_plugins() -> None:
    registry = PluginRegistry(allowed_ids={"a", "b"})
    registry.register(FakePlugin("a", provides=("cap.a",), requires=("cap.b",)))
    registry.register(FakePlugin("b", provides=("cap.b",), requires=("cap.a",)))
    with pytest.raises(ValueError, match="dependency cycle"):
        registry.resolve()


def test_registry_rejects_duplicate_ids_and_unlisted_plugins() -> None:
    registry = PluginRegistry(allowed_ids={"a"})
    registry.register(FakePlugin("a"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakePlugin("a"))

    outside = PluginRegistry(allowed_ids={"a"})
    with pytest.raises(ValueError, match="not allowed"):
        outside.register(FakePlugin("b"))


def test_registry_rejects_missing_capability_dependency() -> None:
    registry = PluginRegistry(allowed_ids={"a", "b"})
    registry.register(FakePlugin("a", requires=("cap.missing",)))
    registry.register(FakePlugin("b"))
    with pytest.raises(ValueError, match="cap.missing"):
        registry.resolve()


def test_registry_rejects_undeclared_capability_conflict() -> None:
    registry = PluginRegistry(allowed_ids={"a", "b"})
    registry.register(FakePlugin("a", provides=("cap.x",)))
    registry.register(FakePlugin("b", provides=("cap.x",)))
    with pytest.raises(ValueError, match="conflict"):
        registry.resolve()


def test_registry_resolves_in_stable_topological_order() -> None:
    registry = PluginRegistry(allowed_ids={"z.sampler", "a.transcriber", "m.core"})
    registry.register(FakePlugin("z.sampler", requires=("cap.core",)))
    registry.register(FakePlugin("a.transcriber", requires=("cap.core",)))
    registry.register(FakePlugin("m.core", provides=("cap.core",)))

    resolved = registry.resolve()
    assert [plugin.manifest.id for plugin in resolved] == [
        "m.core",
        "a.transcriber",
        "z.sampler",
    ]


def test_registry_rejects_duplicate_model_visible_tool_names() -> None:
    registry = PluginRegistry(allowed_ids={"x.sample", "y.sample"})
    registry.register(FakePlugin("x.sample"))
    registry.register(FakePlugin("y.sample"))
    with pytest.raises(ValueError, match="tool name"):
        registry.resolve()


def test_tool_result_defaults_to_unreported_usage() -> None:
    result = ToolResult(status="completed")
    assert result.evidence_ids == ()
    assert result.summary == {}
    assert result.usage.reported is False
    with pytest.raises(ValidationError):
        ToolResult(status="exploded")


def test_tool_execution_context_exposes_only_bounded_capabilities() -> None:
    field_names = {field.name for field in dataclasses.fields(ToolExecutionContext)}
    assert field_names == {
        "source_path",
        "probe",
        "artifact_root",
        "media",
        "recognizer",
        "sampler",
        "evidence_sink",
    }


def test_discovery_loads_only_explicit_allowed_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[str] = []
    allowed = FakePlugin("vidsnap.tool.sample_evidence")
    denied = FakePlugin("vidsnap.tool.open_url")
    entries = FakeEntryPoints((FakeEntryPoint(allowed, loaded), FakeEntryPoint(denied, loaded)))
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: entries)

    discovered = discover_allowed_plugins({"vidsnap.tool.sample_evidence"})

    assert loaded == ["vidsnap.tool.sample_evidence"]
    assert [plugin.manifest.id for plugin in discovered] == ["vidsnap.tool.sample_evidence"]


def test_discovery_rejects_manifest_id_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[str] = []
    impostor = FakePlugin("vidsnap.tool.other")
    entry = FakeEntryPoint(impostor, loaded)
    entry.name = "vidsnap.tool.sample_evidence"
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: FakeEntryPoints((entry,)))

    with pytest.raises(ValueError, match="manifest id"):
        discover_allowed_plugins({"vidsnap.tool.sample_evidence"})


def test_registry_registers_and_resolves_manifest_only_plugin() -> None:
    registry = PluginRegistry(allowed_ids={"vidsnap.policy.guard", "vidsnap.tool.sample"})
    registry.register(ManifestOnlyPlugin("vidsnap.policy.guard", kind="policy"))
    registry.register(FakePlugin("vidsnap.tool.sample"))

    resolved = registry.resolve()
    assert [plugin.manifest.id for plugin in resolved] == [
        "vidsnap.policy.guard",
        "vidsnap.tool.sample",
    ]

    tool = registry.tool_by_name("sample")
    assert tool.manifest.id == "vidsnap.tool.sample"
    with pytest.raises(ValueError, match="no registered tool"):
        registry.tool_by_name("vidsnap.policy.guard")


def test_registry_rejects_registration_after_successful_resolve() -> None:
    registry = PluginRegistry(allowed_ids={"a", "b"})
    registry.register(FakePlugin("a"))
    registry.resolve()

    with pytest.raises(ValueError, match="resolved"):
        registry.register(FakePlugin("b"))
    with pytest.raises(ValueError, match="resolved"):
        registry.register(ManifestOnlyPlugin("b", kind="observer"))


def test_registry_resolve_is_determinantly_repeatable_when_frozen() -> None:
    registry = PluginRegistry(allowed_ids={"a", "b"})
    registry.register(FakePlugin("b"))
    registry.register(ManifestOnlyPlugin("a", kind="task"))

    first = registry.resolve()
    second = registry.resolve()
    assert first == second
    assert [plugin.manifest.id for plugin in second] == ["a", "b"]


def test_registry_tool_by_name_requires_successful_resolve() -> None:
    registry = PluginRegistry(allowed_ids={"a"})
    registry.register(FakePlugin("a"))

    with pytest.raises(ValueError, match="resolve"):
        registry.tool_by_name("a")


def test_registry_failed_resolve_does_not_freeze_registration() -> None:
    registry = PluginRegistry(allowed_ids={"a", "b"})
    registry.register(FakePlugin("a", requires=("cap.missing",)))
    with pytest.raises(ValueError, match="cap.missing"):
        registry.resolve()

    registry.register(FakePlugin("b"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakePlugin("a", provides=("cap.missing",)))


def test_discovery_loads_manifest_only_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[str] = []
    policy = ManifestOnlyPlugin("vidsnap.policy.guard")
    entry = FakeEntryPoint(policy, loaded)  # type: ignore[arg-type]
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: FakeEntryPoints((entry,)))

    discovered = discover_allowed_plugins({"vidsnap.policy.guard"})

    assert loaded == ["vidsnap.policy.guard"]
    assert [plugin.manifest.id for plugin in discovered] == ["vidsnap.policy.guard"]
    assert discovered[0].manifest.kind == "policy"


def test_tool_schemas_match_agent_step_request_shape() -> None:
    registry = PluginRegistry(allowed_ids={"vidsnap.tool.sample"})
    plugin = FakePlugin("vidsnap.tool.sample")
    registry.register(plugin)
    registry.resolve()

    schemas = registry.tool_schemas()

    assert schemas == (
        {"name": plugin.name, "input_schema": plugin.input_model.model_json_schema()},
    )
    assert "arguments" not in schemas[0]
