#!/usr/bin/env python3
"""Inject local Hermes Qwen settings into exactly one child process."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERMES_KEY = "QWEN_TOKEN_PLAN_CN_API_KEY"
_HERMES_URL = "QWEN_TOKEN_PLAN_CN_BASE_URL"


def _read_required_values(path: Path) -> tuple[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeError("Hermes Qwen configuration is unavailable") from error
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key not in {_HERMES_KEY, _HERMES_URL}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    api_key = values.get(_HERMES_KEY, "")
    base_url = values.get(_HERMES_URL, "")
    if not api_key or not base_url:
        raise RuntimeError("Hermes Qwen configuration is incomplete")
    return api_key, base_url


def main() -> None:
    command = sys.argv[1:]
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("a child command is required")
    try:
        api_key, base_url = _read_required_values(Path.home() / ".hermes" / ".env")
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    child_environment = os.environ.copy()
    child_environment["VIDSNAP_QWEN_API_KEY"] = api_key
    child_environment["VIDSNAP_QWEN_BASE_URL"] = base_url
    os.execvpe(command[0], command, child_environment)


if __name__ == "__main__":
    main()
