"""Allow-list-controlled discovery of installed plugin entry points."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable

from vidsnap.plugins.base import Plugin

PLUGIN_ENTRY_POINT_GROUP = "vidsnap.plugins"


def discover_allowed_plugins(allowed_ids: Iterable[str]) -> tuple[Plugin, ...]:
    """Load only entry points whose names are explicitly allow-listed.

    Discovery never implies authorization: an entry point is loaded only when
    its name appears in the operator allow-list, and the loaded manifest ID
    must match the entry-point name exactly.
    """
    allowed = frozenset(allowed_ids)
    discovered: list[Plugin] = []
    entry_points = importlib.metadata.entry_points().select(group=PLUGIN_ENTRY_POINT_GROUP)
    for entry_point in entry_points:
        if entry_point.name not in allowed:
            continue
        factory = entry_point.load()
        plugin = factory()
        manifest_id = plugin.manifest.id
        if manifest_id != entry_point.name:
            raise ValueError(
                f"plugin manifest id '{manifest_id}' does not match "
                f"entry point name '{entry_point.name}'"
            )
        discovered.append(plugin)
    return tuple(discovered)
