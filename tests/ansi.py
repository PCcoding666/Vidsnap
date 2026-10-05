"""Helpers for assertions on styled CLI output."""

import re

_ANSI_CSI_SEQUENCE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    """Return text without ANSI escape sequences.

    CI variables such as GITHUB_ACTIONS make Typer/Rich style --help output,
    splitting option names with escape codes; stripping them keeps substring
    assertions styling-independent.
    """
    return _ANSI_CSI_SEQUENCE.sub("", text)
