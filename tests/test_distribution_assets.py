"""Distribution-level package-data tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

_DEMO_MEDIA_SUFFIXES: tuple[str, ...] = (
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".m4v",
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
)
_DEMO_FORBIDDEN_NAME_PARTS: tuple[str, ...] = (".env", "cookie", "credential", "id_rsa")
_REQUIRED_DEMO_FIXTURE_FILES: frozenset[str] = frozenset(
    {
        "vidsnap/demo/fixtures/provenance.json",
        "vidsnap/demo/fixtures/run/manifest.json",
        "vidsnap/demo/fixtures/run/events.jsonl",
        "vidsnap/demo/fixtures/run/result.json",
    }
)


@pytest.fixture(scope="module")
def wheel_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    outdir = tmp_path_factory.mktemp("distribution")
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(outdir)],
        check=True,
    )
    return next(outdir.glob("vidsnap_harness-*.whl"))


@pytest.fixture(scope="module")
def wheel_names(wheel_path: Path) -> set[str]:
    with ZipFile(wheel_path) as wheel:
        return set(wheel.namelist())


def test_wheel_includes_the_versioned_result_schema(wheel_names: set[str]) -> None:
    assert "vidsnap/contracts/schemas/video_analysis.v1.json" in wheel_names
    assert "vidsnap/prompts/evidence.json" in wheel_names


def test_wheel_includes_the_offline_trace_template(wheel_names: set[str]) -> None:
    assert "vidsnap/trace/assets/trace.html" in wheel_names
    assert "vidsnap/trace/assets/timeline.js" in wheel_names


def test_wheel_packages_the_zero_key_demo_and_its_replay_fixture(
    wheel_names: set[str],
) -> None:
    demo_files = {name for name in wheel_names if name.startswith("vidsnap/demo/")}
    assert demo_files, "the zero-key demo and its packaged fixture must ship in the wheel"

    missing = _REQUIRED_DEMO_FIXTURE_FILES - demo_files
    assert missing == set(), f"demo fixture files missing from the wheel: {sorted(missing)}"

    evidence_files = {
        name
        for name in demo_files
        if name.startswith("vidsnap/demo/fixtures/run/evidence/") and name.endswith(".json")
    }
    assert len(evidence_files) == 11, "the packaged fixture must ship exactly 11 evidence items"


def test_wheel_fixture_provenance_declares_publishable_origin(wheel_path: Path) -> None:
    with ZipFile(wheel_path) as wheel:
        provenance = json.loads(wheel.read("vidsnap/demo/fixtures/provenance.json").decode())
    declared = {str(provenance.get("kind", "")).lower()}
    declared.add(str(provenance.get("license", "")).lower())
    allowed = {"synthetic", "self-owned", "cc0", "cc0-1.0", "public-domain"}
    assert declared & allowed, provenance
    assert provenance["contains_media"] is False
    assert provenance["contains_private_data"] is False
    assert provenance["contains_provider_output"] is False


def test_wheel_demo_fixture_ships_no_media_or_private_payloads(wheel_names: set[str]) -> None:
    demo_files = [name for name in wheel_names if name.startswith("vidsnap/demo/")]
    assert demo_files, "the zero-key demo and its packaged fixture must ship in the wheel"

    for name in demo_files:
        lowered = name.lower()
        assert not lowered.endswith(_DEMO_MEDIA_SUFFIXES), (
            f"media file packaged in the demo fixture: {name}"
        )
        assert not any(part in lowered for part in _DEMO_FORBIDDEN_NAME_PARTS), name
