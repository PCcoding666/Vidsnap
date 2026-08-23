"""Safety boundary for the external manifest preparation command."""

import subprocess
import sys
from pathlib import Path


def test_manifest_preparer_rejects_repository_root() -> None:
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_agentic_manifests.py",
            "--root",
            str(root / "benchmark-private"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "outside the repository" in result.stderr
