"""Every run starts with a versioned header recording what was asked of it.

``run.started`` carries the goal as given, the input's identity (SHA-256 and
byte size), the provider and model when known, the policy, the recipe when
applicable, the resolved plugin versions, and the package version. The probed
input duration is recorded on ``probe.completed`` and repeated on the terminal
run event, because the probe runs after the run has started.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from fakes import FakeFFmpeg, FakeTranscriber, FakeVideoModel
from test_fixed_policy import build_context, make_kernel, read_events

import vidsnap
from vidsnap.config import HarnessConfig
from vidsnap.contracts import HarnessPolicy, TerminalState, VideoGoal, VideoSource
from vidsnap.providers import MockProvider, ProviderIdentity
from vidsnap.runtime import RecipeIdentity
from vidsnap.trace import read_trace
from vidsnap.trace.export import export_trace

_VIDEO_BYTES = b"deterministic-local-video-bytes"
_EXPECTED_PLUGINS = [
    {"id": "vidsnap.tool.sample_evidence", "version": "1.0.0"},
    {"id": "vidsnap.tool.transcribe_audio", "version": "1.0.0"},
]


def _event(run_path: Path, event_type: str) -> dict[str, object]:
    (event,) = [e for e in read_events(run_path) if e.get("event_type") == event_type]
    return event


def _terminal_run_payload(run_path: Path) -> dict[str, object]:
    (event,) = [
        e
        for e in read_events(run_path)
        if str(e.get("event_type", "")).startswith("run.") and e.get("status") != "started"
    ]
    payload = event["payload"]
    assert isinstance(payload, dict)
    return payload


@pytest.mark.asyncio
async def test_run_started_records_the_complete_header(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.provider_identity = ProviderIdentity(
        id="qwen", model="qwen3.8-max", base_url="https://user:pw@example.invalid/v1"
    )
    context.speech_recognizer_identity = ProviderIdentity(
        id="qwen", model="qwen3-asr-flash", base_url="https://example.invalid/v1"
    )
    context.recipe = RecipeIdentity(id="interview", version="9.9.9")

    await make_kernel().run(context)

    started = _event(context.bundle.path, "run.started")
    assert started["payload"] == {
        "schema_version": "vidsnap.run-header/v1",
        "policy": "FixedPolicy",
        "goal": "Describe what happens in the video",
        "required_sections": [],
        "input_sha256": hashlib.sha256(_VIDEO_BYTES).hexdigest(),
        "input_size_bytes": len(_VIDEO_BYTES),
        "provider": {"id": "qwen", "model": "qwen3.8-max"},
        "speech_recognizer": {"id": "qwen", "model": "qwen3-asr-flash"},
        "recipe": {"id": "interview", "version": "9.9.9"},
        "plugins": _EXPECTED_PLUGINS,
        "package_version": vidsnap.__version__,
    }
    ledger = (context.bundle.path / "events.jsonl").read_text(encoding="utf-8")
    assert "example.invalid" not in ledger


@pytest.mark.asyncio
async def test_unknown_identities_stay_null_never_guessed(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.source = VideoSource(path=tmp_path / "missing.mp4")

    result = await make_kernel().run(context)

    assert result.terminal_state is TerminalState.SUCCEEDED
    payload = _event(context.bundle.path, "run.started")["payload"]
    assert payload["input_sha256"] is None
    assert payload["input_size_bytes"] is None
    assert payload["provider"] is None
    assert payload["speech_recognizer"] is None
    assert payload["recipe"] is None


@pytest.mark.asyncio
async def test_goal_records_required_sections_as_given(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    goal = VideoGoal(objective="Summarize for editors", required_sections=("risks", "actions"))
    context.task_adapter.goal = goal

    await make_kernel().run(context)

    payload = _event(context.bundle.path, "run.started")["payload"]
    assert payload["goal"] == "Summarize for editors"
    assert payload["required_sections"] == ["risks", "actions"]


@pytest.mark.asyncio
async def test_probe_duration_is_repeated_on_the_terminal_run_event(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)

    await make_kernel().run(context)

    probe = _event(context.bundle.path, "probe.completed")
    assert probe["payload"]["duration_seconds"] == 8.0
    assert _terminal_run_payload(context.bundle.path)["input_duration_seconds"] == 8.0


@pytest.mark.asyncio
async def test_terminal_duration_is_null_when_the_probe_never_completed(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.policy = context.policy.model_copy(update={"max_wall_seconds": 1})
    ticks = iter([0.0])

    from vidsnap.runtime import FixedPolicy, HarnessKernel, default_plugin_registry

    kernel = HarnessKernel(
        policy=FixedPolicy(),
        registry=default_plugin_registry(),
        clock=lambda: next(ticks, 99.0),
    )
    result = await kernel.run(context)

    assert result.terminal_state is TerminalState.EXHAUSTED
    assert _terminal_run_payload(context.bundle.path)["input_duration_seconds"] is None


@pytest.mark.asyncio
async def test_cancellation_while_hashing_input_still_finalizes_one_truthful_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, media, *_ = build_context(tmp_path, has_audio=True)

    async def cancelled(path: Path) -> object:
        del path
        raise asyncio.CancelledError()

    monkeypatch.setattr("vidsnap.runtime.kernel.read_file_identity", cancelled)

    result = await make_kernel().run(context)

    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason == "cancelled"
    assert media.probe_calls == 0
    assert _event(context.bundle.path, "run.started")["payload"]["input_sha256"] is None
    manifest = json.loads((context.bundle.path / "manifest.json").read_text())
    assert manifest["terminal_state"] == "FAILED"


@pytest.mark.asyncio
async def test_harness_records_the_injected_provider_identity(tmp_path: Path) -> None:
    from vidsnap.harness import VideoHarness

    video = tmp_path / "input.mp4"
    video.write_bytes(_VIDEO_BYTES)
    harness = VideoHarness(media=FakeFFmpeg(has_audio=False), provider=MockProvider())

    result = await harness.run(
        VideoSource(path=video),
        VideoGoal(objective="Summarize"),
        HarnessPolicy(output_dir=tmp_path / "run"),
    )

    payload = _event(result.run_path, "run.started")["payload"]
    assert payload["provider"] == {"id": "mock", "model": "mock"}
    assert payload["speech_recognizer"] is None
    assert payload["input_sha256"] == hashlib.sha256(_VIDEO_BYTES).hexdigest()


@pytest.mark.asyncio
async def test_harness_records_the_default_qwen_stack(tmp_path: Path) -> None:
    from vidsnap.harness import VideoHarness

    video = tmp_path / "input.mp4"
    video.write_bytes(_VIDEO_BYTES)
    harness = VideoHarness(HarnessConfig(api_key=None), media=FakeFFmpeg(has_audio=True))

    for mode in ("fixed", "agentic"):
        result = await harness.run(
            VideoSource(path=video),
            VideoGoal(objective="Summarize"),
            HarnessPolicy(output_dir=tmp_path / mode, tool_mode=mode),
        )
        payload = _event(result.run_path, "run.started")["payload"]
        assert payload["provider"] == {"id": "qwen", "model": "qwen3.8-max"}
        assert payload["speech_recognizer"] == {"id": "qwen", "model": "qwen3-asr-flash"}


@pytest.mark.asyncio
async def test_harness_leaves_custom_ports_unidentified(tmp_path: Path) -> None:
    from vidsnap.harness import VideoHarness

    video = tmp_path / "input.mp4"
    video.write_bytes(_VIDEO_BYTES)
    harness = VideoHarness(
        media=FakeFFmpeg(has_audio=True),
        model=FakeVideoModel(),
        recognizer=_PlainRecognizer(),
    )

    result = await harness.run(
        VideoSource(path=video),
        VideoGoal(objective="Summarize"),
        HarnessPolicy(output_dir=tmp_path / "run"),
    )

    payload = _event(result.run_path, "run.started")["payload"]
    assert payload["provider"] is None
    assert payload["speech_recognizer"] is None


class _PlainRecognizer:
    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        del audio_bytes, mime_type
        return "spoken words"


@pytest.mark.asyncio
async def test_trace_projection_keeps_goal_and_input_but_never_provider_identity(
    tmp_path: Path,
) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.provider_identity = ProviderIdentity(
        id="sentinel-provider-id-5d", model="sentinel-model-name-6e", base_url="https://h/v1"
    )
    context.speech_recognizer_identity = ProviderIdentity(
        id="sentinel-asr-id-7f", model="sentinel-asr-model-8a", base_url="https://h/v1"
    )
    context.recognizer = FakeTranscriber()

    await make_kernel().run(context)

    document = read_trace(context.bundle.path)
    assert document.overview.goal == "Describe what happens in the video"
    assert document.overview.input_sha256 == hashlib.sha256(_VIDEO_BYTES).hexdigest()
    html = export_trace(context.bundle.path, tmp_path / "trace.html").read_text(encoding="utf-8")
    for marker in (
        "sentinel-provider-id-5d",
        "sentinel-model-name-6e",
        "sentinel-asr-id-7f",
        "sentinel-asr-model-8a",
    ):
        assert marker not in document.model_dump_json()
        assert marker not in html


@pytest.mark.asyncio
async def test_unhashable_input_path_still_finalizes_one_truthful_run(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.source = VideoSource(path=Path(f"{tmp_path}/bad\0name.mp4"))

    result = await make_kernel().run(context)

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert _event(context.bundle.path, "run.started")["payload"]["input_sha256"] is None
    manifest = json.loads((context.bundle.path / "manifest.json").read_text())
    assert manifest["finalized_at"] is not None


@pytest.mark.asyncio
async def test_identity_reader_errors_never_escape_the_kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)

    async def broken(path: Path) -> object:
        del path
        raise RuntimeError("identity reader bug")

    monkeypatch.setattr("vidsnap.runtime.kernel.read_file_identity", broken)

    result = await make_kernel().run(context)

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert _event(context.bundle.path, "run.started")["payload"]["input_size_bytes"] is None
