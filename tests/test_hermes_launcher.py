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


def test_hermes_launcher_reads_one_workspace_key_from_csv_for_child_only(tmp_path) -> None:
    """The upload key must reach only the child and must never appear in launcher output."""
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    fake_token_key = "token-plan-secret-must-never-appear"
    fake_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    (hermes_dir / ".env").write_text(
        "QWEN_TOKEN_PLAN_CN_API_KEY=" + fake_token_key + "\n"
        "QWEN_TOKEN_PLAN_CN_BASE_URL=" + fake_url + "\n"
    )
    fake_upload_key = "sk" + "-ws-" + ("x" * 40)
    csv_path = tmp_path / "model-studio.csv"
    csv_path.write_text(
        "name,value\nworkspace," + fake_upload_key + "\nmetadata,not-a-key\n",
        encoding="utf-8",
    )
    child = (
        "import os; "
        "print('token=' + ('SET' if os.getenv('VIDSNAP_QWEN_API_KEY') else 'UNSET')); "
        "value = os.getenv('VIDSNAP_MODEL_STUDIO_UPLOAD_API_KEY'); "
        "print('upload=' + ('SET' if value else 'UNSET'))"
    )
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_with_hermes_qwen.py",
            "--model-studio-key-csv",
            str(csv_path),
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
    assert result.stdout.splitlines() == ["token=SET", "upload=SET"]
    combined_output = result.stdout + result.stderr
    assert fake_token_key not in combined_output
    assert fake_upload_key not in combined_output
    assert fake_url not in combined_output


def test_hermes_launcher_rejects_csv_without_exactly_one_workspace_key(tmp_path) -> None:
    """Missing or ambiguous upload credentials must stop before starting the child."""
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    (hermes_dir / ".env").write_text(
        "QWEN_TOKEN_PLAN_CN_API_KEY=token-plan-secret\n"
        "QWEN_TOKEN_PLAN_CN_BASE_URL="
        "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1\n"
    )
    csv_path = tmp_path / "model-studio.csv"
    csv_path.write_text("name,value\nworkspace,not-a-key\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_with_hermes_qwen.py",
            "--model-studio-key-csv",
            str(csv_path),
            "--",
            sys.executable,
            "-c",
            "raise AssertionError('child must not start')",
        ],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "exactly one Model Studio workspace key" in result.stderr
    assert "child must not start" not in result.stderr
