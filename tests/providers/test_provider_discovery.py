"""RED tests for allow-list-controlled provider entry-point discovery."""

from __future__ import annotations

import importlib.metadata
from typing import Any

import pytest

from vidsnap.providers import MockProvider, ProviderIdentity
from vidsnap.providers.discovery import (
    PROVIDER_ENTRY_POINT_GROUP,
    discover_allowed_providers,
)


def recording_identity(provider_id: str) -> ProviderIdentity:
    return ProviderIdentity(
        id=provider_id,
        model="mock-model",
        base_url="offline://mock",
    )


class RecordingProvider:
    """Runtime-conforming provider double that records lifecycle calls."""

    def __init__(self, identity: ProviderIdentity) -> None:
        self.identity = identity
        self.calls: list[str] = []

    def plan_tools(self, *args: Any) -> Any:
        self.calls.append("plan_tools")
        raise AssertionError("discovery must not call plan_tools")

    def analyze_evidence(self, *args: Any) -> Any:
        self.calls.append("analyze_evidence")
        raise AssertionError("discovery must not call analyze_evidence")

    def decide_next(self, *args: Any) -> Any:
        self.calls.append("decide_next")
        raise AssertionError("discovery must not call decide_next")


class FakeEntryPoint:
    def __init__(self, name: str, factory: Any, loaded: list[str]) -> None:
        self.name = name
        self._factory = factory
        self._loaded = loaded

    def load(self) -> Any:
        self._loaded.append(self.name)
        return self._factory


class FakeEntryPoints(tuple):
    def select(self, *, group: str) -> FakeEntryPoints:
        assert group == "vidsnap.providers"
        return self


def test_provider_entry_point_group_is_namespaced() -> None:
    assert PROVIDER_ENTRY_POINT_GROUP == "vidsnap.providers"


def test_discovery_loads_only_explicitly_allowed_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    allowed = RecordingProvider(recording_identity("vidsnap.provider.sample"))
    denied = RecordingProvider(recording_identity("vidsnap.provider.open_url"))
    entries = FakeEntryPoints(
        (
            FakeEntryPoint("vidsnap.provider.sample", lambda: allowed, loaded),
            FakeEntryPoint("vidsnap.provider.open_url", lambda: denied, loaded),
        )
    )
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: entries)

    discovered = discover_allowed_providers({"vidsnap.provider.sample"})

    assert loaded == ["vidsnap.provider.sample"]
    assert discovered == (allowed,)
    assert allowed.calls == []


def test_loaded_zero_argument_factory_returns_runtime_conforming_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    provider = MockProvider()
    entry_name = provider.identity.id
    factory_args: list[tuple[Any, ...]] = []

    def factory(*args: Any) -> MockProvider:
        factory_args.append(args)
        return provider

    entry = FakeEntryPoint(entry_name, factory, loaded)
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: FakeEntryPoints((entry,)))

    discovered = discover_allowed_providers({entry_name})

    assert loaded == [entry_name]
    assert factory_args == [()]
    assert discovered == (provider,)
    assert discovered[0].identity.id == entry_name
    for method in ("plan_tools", "analyze_evidence", "decide_next"):
        assert callable(getattr(discovered[0], method))


def test_entry_point_name_must_equal_provider_identity_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    impostor = RecordingProvider(recording_identity("vidsnap.provider.other"))
    entry = FakeEntryPoint("vidsnap.provider.sample", lambda: impostor, loaded)
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: FakeEntryPoints((entry,)))

    with pytest.raises(ValueError, match="identity"):
        discover_allowed_providers({"vidsnap.provider.sample"})

    assert loaded == ["vidsnap.provider.sample"]


def test_discovery_never_invokes_provider_lifecycle_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    provider = RecordingProvider(recording_identity("vidsnap.provider.sample"))
    entry = FakeEntryPoint("vidsnap.provider.sample", lambda: provider, loaded)
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: FakeEntryPoints((entry,)))

    discover_allowed_providers({"vidsnap.provider.sample"})

    assert provider.calls == []


def test_non_callable_loaded_object_raises_value_error_naming_entry_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    allowed = FakeEntryPoint("vidsnap.provider.sample", object(), loaded)
    denied = FakeEntryPoint(
        "vidsnap.provider.open_url",
        lambda: RecordingProvider(recording_identity("vidsnap.provider.open_url")),
        loaded,
    )
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: FakeEntryPoints((allowed, denied)),
    )

    with pytest.raises(ValueError, match=r"vidsnap\.provider\.sample"):
        discover_allowed_providers({"vidsnap.provider.sample"})

    assert loaded == ["vidsnap.provider.sample"]


def test_factory_requiring_positional_argument_raises_value_error_naming_entry_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    factory_calls: list[tuple[Any, ...]] = []

    def factory(needs_identity: ProviderIdentity) -> RecordingProvider:
        factory_calls.append((needs_identity,))
        return RecordingProvider(recording_identity("vidsnap.provider.sample"))

    allowed = FakeEntryPoint("vidsnap.provider.sample", factory, loaded)
    denied = FakeEntryPoint(
        "vidsnap.provider.open_url",
        lambda: RecordingProvider(recording_identity("vidsnap.provider.open_url")),
        loaded,
    )
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: FakeEntryPoints((allowed, denied)),
    )

    with pytest.raises(ValueError, match=r"vidsnap\.provider\.sample"):
        discover_allowed_providers({"vidsnap.provider.sample"})

    assert loaded == ["vidsnap.provider.sample"]
    assert factory_calls == []
