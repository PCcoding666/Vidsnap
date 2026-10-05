"""Offline contract test for the plugin-template video_metadata TOOL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from video_metadata.plugin import TOOL

from vidsnap.plugins.base import EvidenceSink, FFmpegPort, ToolExecutionContext
from vidsnap.video.probe import MediaProbe
from vidsnap.video.sampling import AdaptiveSampler

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_RUN = TEMPLATE_ROOT / "example_run"


def _load_probe() -> MediaProbe:
    payload = json.loads((EXAMPLE_RUN / "probe.json").read_text(encoding="utf-8"))
    return MediaProbe(**payload)


def _load_expected() -> dict[str, object]:
    payload = json.loads((EXAMPLE_RUN / "expected_result.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _make_context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        source_path=tmp_path / "video.mp4",
        probe=_load_probe(),
        artifact_root=tmp_path / "artifacts",
        media=cast(FFmpegPort, None),
        recognizer=None,
        sampler=AdaptiveSampler(),
        evidence_sink=cast(EvidenceSink, None),
    )


@pytest.mark.asyncio
async def test_tool_is_deterministic_and_matches_expected_result(tmp_path: Path) -> None:
    plugin = TOOL()
    context = _make_context(tmp_path)
    arguments = plugin.input_model()

    first = await plugin.execute(arguments, context)
    second = await plugin.execute(arguments, context)

    assert first == second
    assert first.model_dump(mode="json") == _load_expected()
    assert not (tmp_path / "artifacts").exists()
