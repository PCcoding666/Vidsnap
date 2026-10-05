"""RED: the app-selected provider must stay fixed and recorded across a run."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

import pytest

from tests.runtime.fakes import FakeFFmpeg
from vidsnap.contracts import HarnessPolicy, VideoGoal, VideoSource
from vidsnap.harness import VideoHarness
from vidsnap.providers import MockProvider
from vidsnap.providers.base import AgentStepRequest

FORBIDDEN_STEP_FIELDS = {"provider", "model", "base_url"}


@pytest.mark.asyncio
async def test_provider_identity_locked_for_full_agentic_run(tmp_path: Path) -> None:
    provider = MockProvider()
    identity_before = provider.identity
    identity_data = asdict(identity_before)
    source_path = tmp_path / "clip.mp4"
    source_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    output_dir = tmp_path / "run"

    harness = VideoHarness(
        provider=provider,
        media=FakeFFmpeg(has_audio=False),
    )
    await harness.run(
        source=VideoSource(path=source_path),
        goal=VideoGoal(objective="Summarize the clip."),
        policy=HarnessPolicy(tool_mode="agentic", output_dir=output_dir),
    )

    manifests = list(output_dir.rglob("manifest.json"))
    assert manifests, "run bundle manifest.json must exist under the output dir"
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["terminal_state"] not in (None, "FAILED", "BLOCKED")

    assert provider.identity == identity_before
    assert set(manifest["provider"]) == {"id", "model", "base_url"}
    assert manifest["provider"]["id"] == identity_data["id"]
    assert manifest["provider"]["model"] == identity_data["model"]
    assert manifest["provider"]["base_url"] == identity_data["base_url"]

    step_fields = {item.name for item in fields(AgentStepRequest)}
    assert not step_fields & FORBIDDEN_STEP_FIELDS
