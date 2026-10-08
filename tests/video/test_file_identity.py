"""Input identity hashes regular files only and never blocks or raises."""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

import pytest

from vidsnap.video.identity import FileIdentity, file_identity


def _identity_within(path: Path, seconds: float = 5.0) -> object:
    """Run file_identity in a daemon thread so a regression fails instead of hanging."""
    outcome: dict[str, object] = {}

    def target() -> None:
        try:
            outcome["value"] = file_identity(path)
        except BaseException as error:  # pragma: no cover - the assertion reports it
            outcome["error"] = error

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(seconds)
    assert not worker.is_alive(), f"file_identity blocked on {path}"
    assert "error" not in outcome, outcome.get("error")
    return outcome["value"]


def test_regular_file_is_hashed_with_its_size(tmp_path: Path) -> None:
    path = tmp_path / "input.mp4"
    path.write_bytes(b"x" * 3_000_000)

    assert _identity_within(path) == FileIdentity(
        sha256=hashlib.sha256(b"x" * 3_000_000).hexdigest(), size_bytes=3_000_000
    )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_named_pipe_is_not_read(tmp_path: Path) -> None:
    pipe = tmp_path / "input.mp4"
    os.mkfifo(pipe)

    assert _identity_within(pipe) is None


@pytest.mark.skipif(not Path("/dev/zero").exists(), reason="needs /dev/zero")
def test_device_file_is_not_read() -> None:
    assert _identity_within(Path("/dev/zero")) is None


def test_directory_missing_file_and_nul_byte_paths_record_null(tmp_path: Path) -> None:
    assert _identity_within(tmp_path) is None
    assert _identity_within(tmp_path / "missing.mp4") is None
    assert _identity_within(Path(f"{tmp_path}/bad\0name.mp4")) is None
