"""The agentic benchmark README must match the registered runner contract."""

from __future__ import annotations

from pathlib import Path

README_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "agentic" / "README.md"


def _read_protocol() -> str:
    return README_PATH.read_text(encoding="utf-8")


def _composition_section(text: str) -> str:
    marker = "## Registered composition"
    assert marker in text
    section = text.split(marker, 1)[1]
    return section.split("\n## ", 1)[0]


def test_smoke_is_short_video_only_and_cannot_authorize_formal_run() -> None:
    text = _read_protocol()
    composition = _composition_section(text)

    # scripts/run_agentic_benchmark.py requires smoke duration strata == {"short"}.
    assert "only short" in composition
    assert "short, medium, and long" not in composition

    # Smoke reports are marked short_video_only and the runner rejects them as a
    # formal gate, so the README must not present smoke as unlocking formal.
    assert "short_video_only" in text
    assert "cannot authorize" in text
    assert "can unlock formal execution" not in text


def test_direct_always_uses_complete_2fps_timeline_not_video_first_fallback() -> None:
    text = _read_protocol()
    composition = _composition_section(text)

    # The runner hard-codes Direct to frames_2fps and rejects any other mode.
    assert "Direct always" in composition
    assert "2 fps" in composition

    # Direct must not be described as attempting complete-video input first.
    assert "Direct first attempts complete-video input" not in composition
    assert "fallback" not in composition.lower()
