"""Distribution-level package-data tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


def test_wheel_includes_the_versioned_result_schema(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        check=True,
    )

    wheel_path = next(tmp_path.glob("vidsnap_harness-*.whl"))
    with ZipFile(wheel_path) as wheel:
        assert "vidsnap/contracts/schemas/video_analysis.v1.json" in wheel.namelist()
        assert "vidsnap/prompts/evidence.json" in wheel.namelist()
