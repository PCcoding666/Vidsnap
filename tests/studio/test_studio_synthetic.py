"""Packaged synthetic exploration fixture: labeled demos, never real data."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from vidsnap.studio.manifest import StudioManifest

EXPECTED_LABELS = (
    "Simple prompt",
    "A bigger model",
    "Adaptive thinking",
    "A better prompt",
    "Generate evaluate repair",
)


def _load_fixture_text() -> str:
    return (
        files("vidsnap.studio")
        .joinpath("assets/synthetic_exploration.json")
        .read_text(encoding="utf-8")
    )


def test_packaged_fixture_validates_as_studio_manifest() -> None:
    manifest = StudioManifest.model_validate_json(_load_fixture_text())
    assert manifest.api_version == "vidsnap.studio/v1"
    assert manifest.exploration is not None
    assert manifest.iteration is None


def test_five_representative_approach_labels_in_order() -> None:
    manifest = StudioManifest.model_validate_json(_load_fixture_text())
    assert manifest.exploration is not None
    labels = tuple(approach.label for approach in manifest.exploration.approaches)
    assert labels == EXPECTED_LABELS


def test_every_fixture_node_is_marked_synthetic() -> None:
    manifest = StudioManifest.model_validate_json(_load_fixture_text())
    assert manifest.exploration is not None
    assert manifest.exploration.approaches
    assert all(approach.synthetic for approach in manifest.exploration.approaches)


def test_fixture_references_no_real_paths() -> None:
    manifest = StudioManifest.model_validate_json(_load_fixture_text())
    assert manifest.exploration is not None
    references = [
        trial.run for approach in manifest.exploration.approaches for trial in approach.trials
    ]
    assert references
    for reference in references:
        assert reference.startswith("synthetic/")


def test_fixture_carries_no_measured_values_or_sensitive_shapes() -> None:
    raw = _load_fixture_text()
    for forbidden in (
        "/Users/",
        "/home/",
        "https://",
        "http://",
        "api_key",
        "Bearer",
        "passed_trials",
        "latency_ms",
        "total_tokens",
    ):
        assert forbidden not in raw
    payload = json.loads(raw)
    assert payload["api_version"] == "vidsnap.studio/v1"


def test_source_asset_is_present_and_exempt_from_the_json_ignore_rule() -> None:
    source_root = Path(__file__).resolve().parents[2]
    asset = source_root / "src/vidsnap/studio/assets/synthetic_exploration.json"
    assert asset.is_file()
    gitignore = (source_root / ".gitignore").read_text(encoding="utf-8")
    assert "*.json" in gitignore
    assert "!src/vidsnap/studio/assets/synthetic_exploration.json" in gitignore.splitlines()
