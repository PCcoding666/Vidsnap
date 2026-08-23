#!/usr/bin/env python3
"""Inject local Hermes Qwen settings into exactly one child process."""

from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

_HERMES_KEY = "QWEN_TOKEN_PLAN_CN_API_KEY"
_HERMES_URL = "QWEN_TOKEN_PLAN_CN_BASE_URL"
_WORKSPACE_KEY_ENV = "VIDSNAP_MODEL_STUDIO_UPLOAD_API_KEY"
_WORKSPACE_KEY_PATTERN = re.compile(r"sk-ws-[A-Za-z0-9._-]{16,}")


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


def _read_workspace_key(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            values = [cell.strip() for row in csv.reader(handle) for cell in row]
    except (OSError, UnicodeError, csv.Error):
        raise RuntimeError("Model Studio key CSV is unavailable") from None
    candidates = [value for value in values if _WORKSPACE_KEY_PATTERN.fullmatch(value)]
    if len(candidates) != 1:
        raise RuntimeError("Model Studio CSV must contain exactly one Model Studio workspace key")
    return candidates[0]


def _parse_command(arguments: list[str]) -> tuple[Path | None, list[str]]:
    workspace_key_csv: Path | None = None
    command = arguments
    if command[:1] == ["--model-studio-key-csv"]:
        if len(command) < 3:
            raise RuntimeError("Model Studio key CSV path is required")
        workspace_key_csv = Path(command[1])
        command = command[2:]
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise RuntimeError("a child command is required")
    return workspace_key_csv, command


def main() -> None:
    try:
        workspace_key_csv, command = _parse_command(sys.argv[1:])
        api_key, base_url = _read_required_values(Path.home() / ".hermes" / ".env")
        upload_api_key = (
            _read_workspace_key(workspace_key_csv) if workspace_key_csv is not None else None
        )
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    child_environment = os.environ.copy()
    child_environment["VIDSNAP_QWEN_API_KEY"] = api_key
    child_environment["VIDSNAP_QWEN_BASE_URL"] = base_url
    if upload_api_key is not None:
        child_environment[_WORKSPACE_KEY_ENV] = upload_api_key
    os.execvpe(command[0], command, child_environment)


if __name__ == "__main__":
    main()
