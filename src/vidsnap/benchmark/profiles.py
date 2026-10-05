"""Local-path benchmark profiles; this package never downloads or ships datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vidsnap.config import QWEN_MODEL


@dataclass(frozen=True, slots=True)
class BenchmarkProfile:
    """Dataset provenance plus a user-provided local root directory."""

    name: str
    local_root: Path
    license: str
    expected_sha256: str | None = None
    model: str = QWEN_MODEL

    def __post_init__(self) -> None:
        """Pin every benchmark profile to the single approved model."""
        if self.model != QWEN_MODEL:
            raise ValueError(
                f"benchmark profile model must be exactly {QWEN_MODEL!r}, got {self.model!r}"
            )

    def validate_local_root(self) -> None:
        """Require an existing local dataset path instead of downloading data."""
        if not self.local_root.is_dir():
            raise FileNotFoundError(
                f"benchmark dataset is not available locally: {self.local_root}"
            )


CORE_OPEN = "core-open"
RESEARCH_LONG = "research-long"
