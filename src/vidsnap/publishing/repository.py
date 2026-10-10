"""Deterministic repository-root detection for publishing path boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import vidsnap


def find_repository_root(start: Path) -> Path:
    """Return the nearest marked ancestor of one start path, resolved.

    Unmarked start trees repeat the walk from the installed vidsnap package so
    editable installs still protect their real repository; only a package with
    no marked ancestor falls back to the package directory itself.
    """
    package_dir = Path(vidsnap.__file__).resolve().parent
    for origin in (start.resolve(), package_dir):
        for candidate in _ancestors(origin):
            if _is_repository_root(candidate):
                return candidate
    return package_dir


def _ancestors(resolved: Path) -> Iterator[Path]:
    yield resolved
    yield from resolved.parents


def _is_repository_root(candidate: Path) -> bool:
    if (candidate / ".git").exists():
        return True
    return (candidate / "pyproject.toml").is_file() and (candidate / "src" / "vidsnap").is_dir()
