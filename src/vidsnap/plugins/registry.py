"""Dependency-checked, allow-listed plugin assembly before a run starts."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import JsonValue

from vidsnap.plugins.base import Plugin, ToolPlugin


class PluginRegistry:
    """Assemble approved plugins exactly once; runs may never mutate them."""

    def __init__(self, allowed_ids: Iterable[str]) -> None:
        self._allowed_ids = frozenset(allowed_ids)
        self._plugins: dict[str, Plugin] = {}
        self._resolved: tuple[Plugin, ...] | None = None

    def register(self, plugin: Plugin) -> None:
        """Accept one allow-listed plugin and reject duplicate IDs."""
        if self._resolved is not None:
            raise ValueError("registry is already resolved; runs may not mutate plugins")
        manifest = plugin.manifest
        if manifest.id not in self._allowed_ids:
            raise ValueError(f"plugin is not allowed: {manifest.id}")
        if manifest.id in self._plugins:
            raise ValueError(f"plugin is already registered: {manifest.id}")
        self._plugins[manifest.id] = plugin

    def resolve(self) -> tuple[Plugin, ...]:
        """Validate capabilities and return plugins in stable topological order."""
        if self._resolved is not None:
            return self._resolved
        self._check_tool_protocol_conformance()
        providers = self._capability_providers()
        self._check_requirements(providers)
        self._check_tool_names()

        remaining = set(self._plugins)
        resolved: list[Plugin] = []
        satisfied: set[str] = set()
        while remaining:
            ready = sorted(
                plugin_id
                for plugin_id in remaining
                if all(
                    capability in satisfied
                    for capability in self._plugins[plugin_id].manifest.requires
                )
            )
            if not ready:
                raise ValueError(f"plugin dependency cycle among: {', '.join(sorted(remaining))}")
            for plugin_id in ready:
                plugin = self._plugins[plugin_id]
                resolved.append(plugin)
                satisfied.update(plugin.manifest.provides)
                remaining.discard(plugin_id)
        self._resolved = tuple(resolved)
        return self._resolved

    def tool_by_name(self, name: str) -> ToolPlugin:
        """Resolve one resolved model-visible tool plugin by its stable name."""
        if self._resolved is None:
            raise ValueError("resolve() must succeed before tool lookup")
        for plugin in self._resolved:
            if plugin.manifest.kind != "tool" or not isinstance(plugin, ToolPlugin):
                continue
            if not plugin.manifest.model_visible:
                continue
            if plugin.name == name:
                return plugin
        raise ValueError(f"no registered tool is named: {name}")

    def tool_schemas(self) -> tuple[dict[str, JsonValue], ...]:
        """Describe every resolved, model-visible tool for agent decision requests."""
        if self._resolved is None:
            raise ValueError("resolve() must succeed before schema lookup")
        schemas: list[dict[str, JsonValue]] = []
        for plugin in self._resolved:
            if plugin.manifest.kind != "tool" or not isinstance(plugin, ToolPlugin):
                continue
            if not plugin.manifest.model_visible:
                continue
            schemas.append(
                {"name": plugin.name, "arguments": plugin.input_model.model_json_schema()}
            )
        return tuple(schemas)

    def _check_tool_protocol_conformance(self) -> None:
        for plugin_id in sorted(self._plugins):
            plugin = self._plugins[plugin_id]
            if plugin.manifest.kind == "tool" and not isinstance(plugin, ToolPlugin):
                raise ValueError(
                    f"plugin '{plugin_id}' declares kind 'tool' but does not "
                    "satisfy the ToolPlugin protocol"
                )

    def _capability_providers(self) -> dict[str, str]:
        providers: dict[str, str] = {}
        for plugin_id in sorted(self._plugins):
            for capability in self._plugins[plugin_id].manifest.provides:
                if capability in providers:
                    raise ValueError(
                        f"undeclared capability conflict for '{capability}': "
                        f"{providers[capability]} and {plugin_id}"
                    )
                providers[capability] = plugin_id
        return providers

    def _check_requirements(self, providers: dict[str, str]) -> None:
        for plugin_id in sorted(self._plugins):
            for capability in self._plugins[plugin_id].manifest.requires:
                if capability not in providers:
                    raise ValueError(
                        f"plugin '{plugin_id}' requires missing capability '{capability}'"
                    )

    def _check_tool_names(self) -> None:
        names: dict[str, str] = {}
        for plugin_id in sorted(self._plugins):
            plugin = self._plugins[plugin_id]
            if plugin.manifest.kind != "tool" or not isinstance(plugin, ToolPlugin):
                continue
            if not plugin.manifest.model_visible:
                continue
            if plugin.name in names:
                raise ValueError(
                    f"duplicate model-visible tool name '{plugin.name}': "
                    f"{names[plugin.name]} and {plugin_id}"
                )
            names[plugin.name] = plugin_id
