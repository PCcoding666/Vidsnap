"""Distribution tests: packaged studio assets and installed-wheel export."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest

_STUDIO_ASSETS: tuple[str, ...] = (
    "vidsnap/studio/assets/studio.html",
    "vidsnap/studio/assets/studio.js",
    "vidsnap/studio/assets/synthetic_exploration.json",
)
_STUDIO_MODULE_FILES: frozenset[str] = frozenset(
    {
        "vidsnap/studio/__init__.py",
        "vidsnap/studio/manifest.py",
        "vidsnap/studio/project.py",
        "vidsnap/studio/export.py",
    }
)


def _clean_env() -> dict[str, str]:
    """A subprocess environment that cannot leak PYTHONPATH or the active venv."""
    env = {
        key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "VIRTUAL_ENV")
    }
    return env


def _site_packages(python: Path) -> Path:
    relative = subprocess.run(
        [str(python), "-c", "import site; print(site.getsitepackages()[0])"],
        check=True,
        capture_output=True,
        text=True,
        env=_clean_env(),
    ).stdout.strip()
    return Path(relative)


@pytest.fixture(scope="module")
def build_outdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    outdir = tmp_path_factory.mktemp("studio-distribution")
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(outdir)],
        check=True,
        env=_clean_env(),
    )
    return outdir


@pytest.fixture(scope="module")
def wheel_path(build_outdir: Path) -> Path:
    return next(build_outdir.glob("vidsnap_harness-*.whl"))


@pytest.fixture(scope="module")
def sdist_path(build_outdir: Path) -> Path:
    return next(build_outdir.glob("vidsnap_harness-*.tar.gz"))


@pytest.fixture(scope="module")
def wheel_names(wheel_path: Path) -> set[str]:
    with ZipFile(wheel_path) as wheel:
        return set(wheel.namelist())


def test_wheel_packages_the_studio_assets(wheel_names: set[str]) -> None:
    for asset in _STUDIO_ASSETS:
        assert asset in wheel_names


def test_wheel_studio_entries_carry_no_media_runs_or_credentials(wheel_names: set[str]) -> None:
    studio_files = {name for name in wheel_names if name.startswith("vidsnap/studio/")}
    assert studio_files == _STUDIO_MODULE_FILES | set(_STUDIO_ASSETS)


def test_sdist_packages_the_studio_assets(sdist_path: Path) -> None:
    with tarfile.open(sdist_path, "r:gz") as archive:
        names = set(archive.getnames())
    for asset in ("studio.html", "studio.js", "synthetic_exploration.json"):
        assert any(name.endswith(f"src/vidsnap/studio/assets/{asset}") for name in names)


@pytest.fixture(scope="module")
def installed_venv(wheel_path: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fresh venv where vidsnap comes only from the built wheel.

    Runtime dependencies are resolved from the current interpreter's
    site-packages via a ``.pth`` link, so the install stays fully offline.
    """
    venv_dir = tmp_path_factory.mktemp("studio-venv") / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        env=_clean_env(),
    )
    python = venv_dir / "bin" / "python"
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel_path)],
        check=True,
        capture_output=True,
        env=_clean_env(),
    )
    dependency_link = _site_packages(python) / "vidsnap-studio-test-deps.pth"
    dependency_link.write_text(f"{_site_packages(Path(sys.executable))}\n", encoding="utf-8")
    return venv_dir


def test_installed_wheel_exports_studio_html(
    installed_venv: Path, tmp_path: Path, build_bundle
) -> None:
    root = tmp_path / "installed-root"
    build_bundle(root, "runs/v0/case-01/t1", verify=(True, ()))
    manifest_path = root / "studio.json"
    manifest_path.write_text(
        json.dumps(
            {
                "api_version": "vidsnap.studio/v1",
                "iteration": {
                    "agent_id": "installed-agent",
                    "versions": [
                        {
                            "version": "v0",
                            "summary": "baseline",
                            "cases": [
                                {
                                    "case_id": "case-01",
                                    "trials": [{"trial_id": "t1", "run": "runs/v0/case-01/t1"}],
                                }
                            ],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "installed.html"

    result = subprocess.run(
        [
            str(installed_venv / "bin" / "vidsnap"),
            "studio",
            "export",
            str(manifest_path),
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=_clean_env(),
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert str(output.resolve()) in result.stdout
    assert "vidsnap.studio.projection/v1" in output.read_text(encoding="utf-8")
