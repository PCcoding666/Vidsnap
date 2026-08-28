"""Entry-point discovery for explicitly allowed provider plugins."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable

from vidsnap.providers.base import ProviderIdentity, ProviderPlugin, ProviderProtocol

PROVIDER_ENTRY_POINT_GROUP = "vidsnap.providers"


def discover_allowed_providers(allowed_ids: Iterable[str]) -> tuple[ProviderPlugin, ...]:
    """Load only explicitly allowed provider entry points, preserving entry-point order.

    Each entry point must name a zero-argument provider factory. Candidates must
    satisfy the runtime ``ProviderProtocol`` contract and expose a valid
    ``ProviderIdentity`` whose ``id`` equals the entry-point name. Discovery
    never invokes any model port.
    """
    allowed = set(allowed_ids)
    providers: list[ProviderPlugin] = []
    for entry_point in importlib.metadata.entry_points().select(group=PROVIDER_ENTRY_POINT_GROUP):
        if entry_point.name not in allowed:
            continue
        factory = entry_point.load()
        if not callable(factory):
            raise ValueError(
                f"provider entry point {entry_point.name!r} in group "
                f"{PROVIDER_ENTRY_POINT_GROUP!r} did not load a callable "
                "zero-argument provider factory"
            )
        try:
            candidate = factory()
        except TypeError as error:
            raise ValueError(
                f"provider entry point {entry_point.name!r} in group "
                f"{PROVIDER_ENTRY_POINT_GROUP!r} does not expose a "
                "zero-argument provider factory"
            ) from error
        if not isinstance(candidate, ProviderProtocol):
            raise ValueError(
                f"provider entry point {entry_point.name!r} in group "
                f"{PROVIDER_ENTRY_POINT_GROUP!r} does not conform to the "
                "runtime ProviderProtocol contract"
            )
        # Runtime conformance above is the structural Plugin qualification.
        provider = candidate
        identity = provider.identity
        if (
            not isinstance(identity, ProviderIdentity)
            or not identity.id
            or not identity.model
            or not identity.base_url
        ):
            raise ValueError(
                f"provider entry point {entry_point.name!r} in group "
                f"{PROVIDER_ENTRY_POINT_GROUP!r} exposed an invalid identity"
            )
        if identity.id != entry_point.name:
            raise ValueError(
                f"provider identity {identity.id!r} does not match its entry-point "
                f"name {entry_point.name!r} in group {PROVIDER_ENTRY_POINT_GROUP!r}"
            )
        providers.append(provider)
    return tuple(providers)
