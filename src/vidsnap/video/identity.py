"""Content identity of one local input file, computed without decoding media."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

_BLOCK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """The SHA-256 digest and byte size of one local file."""

    sha256: str
    size_bytes: int


def file_identity(path: Path) -> FileIdentity | None:
    """Hash one regular local file; return ``None`` when it cannot be read."""
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(_BLOCK_BYTES), b""):
                digest.update(block)
                size += len(block)
    except OSError:
        return None
    return FileIdentity(sha256=digest.hexdigest(), size_bytes=size)


async def read_file_identity(path: Path) -> FileIdentity | None:
    """Hash one local file in a worker thread so the event loop stays responsive."""
    return await asyncio.to_thread(file_identity, path)
