"""Content identity of one local input file, computed without decoding media."""

from __future__ import annotations

import asyncio
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

_BLOCK_BYTES = 1024 * 1024
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """The SHA-256 digest and byte size of one local file."""

    sha256: str
    size_bytes: int


def file_identity(path: Path) -> FileIdentity | None:
    """Hash one regular local file; return ``None`` for anything else or on any error.

    The file is opened without blocking and checked on the open descriptor, so
    pipes, devices, and directories are never read. Exactly the size observed at
    open is hashed; a file that shrinks meanwhile records ``None``.
    """
    try:
        descriptor = os.open(path, _OPEN_FLAGS)
    except (OSError, ValueError):
        return None
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            return None
        digest = hashlib.sha256()
        remaining = status.st_size
        while remaining > 0:
            block = os.read(descriptor, min(_BLOCK_BYTES, remaining))
            if not block:
                return None
            digest.update(block)
            remaining -= len(block)
    except (OSError, ValueError):
        return None
    finally:
        os.close(descriptor)
    return FileIdentity(sha256=digest.hexdigest(), size_bytes=status.st_size)


async def read_file_identity(path: Path) -> FileIdentity | None:
    """Hash one local file in a worker thread so the event loop stays responsive."""
    return await asyncio.to_thread(file_identity, path)
