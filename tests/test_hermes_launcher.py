"""Hermes child-process credential injection without disclosure."""

from __future__ import annotations

import os
import subprocess
import sys


def test_hermes_launcher_injects_only_child_variables_without_printing_values(tmp_path) -> None:
    """Printing or omitting either Hermes value must fail this test."""
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    fake_key = "benchmark-secret-must-never-appear"
    fake_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    (hermes_dir / ".env").write_text(
        "QWEN_TOKEN_PLAN_CN_API_KEY=" + fake_key + "\n"
        "QWEN_TOKEN_PLAN_CN_BASE_URL=" + fake_url + "\n"
    )
    child = (
        "import os; print('key=' + ('SET' if os.getenv('VIDSNAP_QWEN_API_KEY') else 'UNSET')); "
        "print('url=' + ('SET' if os.getenv('VIDSNAP_QWEN_BASE_URL') else 'UNSET'))"
    )
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_with_hermes_qwen.py",
            "--",
            sys.executable,
            "-c",
            child,
        ],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["key=SET", "url=SET"]
    assert fake_key not in result.stdout + result.stderr
    assert fake_url not in result.stdout + result.stderr
