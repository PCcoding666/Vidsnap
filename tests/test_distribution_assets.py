"""Distribution-level package-data tests."""

from __future__ import annotations

import subprocess
import sys
from zipfile import ZipFile

import pytest


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    outdir = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir)],
        check=True,
    )
    wheel_path = next(outdir.glob("vidsnap_harness-*.whl"))
    with ZipFile(wheel_path) as wheel:
        return set(wheel.namelist())


def test_wheel_includes_the_versioned_result_schema(wheel_names: set[str]) -> None:
    assert "vidsnap/contracts/schemas/video_analysis.v1.json" in wheel_names
    assert "vidsnap/prompts/evidence.json" in wheel_names


def test_wheel_includes_the_offline_trace_template(wheel_names: set[str]) -> None:
    assert "vidsnap/trace/assets/trace.html" in wheel_names
    assert "vidsnap/trace/assets/timeline.js" in wheel_names
