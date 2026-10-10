"""Interview recipe runs keep their RunBundle when the caller names where.

``InterviewRecipeRunner.run(..., run_dir=...)`` keeps the finalized bundle at
``run_dir`` whatever the outcome, and reports it as ``run_path``. The output
directory still holds exactly the four recipe artifacts. Without ``run_dir``
the library keeps its v0.1.0 behavior: a private temporary bundle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_interview_runner import (
    FakeInterviewMedia,
    FakeInterviewTranscriber,
    ScriptedInterviewAgent,
    interview_final_payload,
    ungrounded_interview_payload,
)

import vidsnap
from vidsnap.config import HarnessConfig
from vidsnap.contracts import AgentDecision, TerminalState, ToolCallRequest, VideoSource
from vidsnap.providers import MockProvider
from vidsnap.recipes import InterviewRecipeRunner
from vidsnap.recipes.runner import _INTERVIEW_OBJECTIVE
from vidsnap.video.sampling import AdaptiveSampler

_FOUR_ARTIFACTS = {"transcript.zh.md", "interview.article.md", "brief.md", "trace.html"}


def _video(tmp_path: Path) -> VideoSource:
    path = tmp_path / "interview.mp4"
    path.write_bytes(b"deterministic-local-interview-video-bytes")
    return VideoSource(path=path)


def _manifest(run_path: Path) -> dict[str, object]:
    return json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))


def _run_started(run_path: Path) -> dict[str, object]:
    for line in (run_path / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event_type") == "run.started":
            return event["payload"]
    raise AssertionError("run.started missing")


def _succeeding_agent() -> ScriptedInterviewAgent:
    return ScriptedInterviewAgent(
        [
            AgentDecision(
                kind="tool_calls",
                calls=(ToolCallRequest(name="transcribe_audio", arguments={}),),
            ),
            AgentDecision(
                kind="tool_calls",
                calls=(ToolCallRequest(name="sample_evidence", arguments={"max_frames": 1}),),
            ),
            AgentDecision(kind="final", output=interview_final_payload()),
        ]
    )


@pytest.mark.asyncio
async def test_success_keeps_the_bundle_and_exactly_four_artifacts(tmp_path: Path) -> None:
    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key="not-a-real-key"),
        media=FakeInterviewMedia(),
        recognizer=FakeInterviewTranscriber(),
        sampler=AdaptiveSampler(),
        agent_model=_succeeding_agent(),
    )
    output_dir = tmp_path / "out"
    run_dir = tmp_path / "runs" / "one"

    result = await runner.run(_video(tmp_path), output_dir, run_dir=run_dir)

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.run_path == run_dir.resolve()
    assert {entry.name for entry in output_dir.iterdir()} == _FOUR_ARTIFACTS
    assert _manifest(run_dir)["terminal_state"] == "SUCCEEDED"
    assert (run_dir / "result.json").is_file()
    header = _run_started(run_dir)
    assert header["recipe"] == {"id": "interview", "version": vidsnap.__version__}
    assert header["goal"] == _INTERVIEW_OBJECTIVE
    assert header["policy"] == "AgenticPolicy"
    # Injected test doubles declare no identity, so none is invented.
    assert header["provider"] is None
    assert header["speech_recognizer"] is None


@pytest.mark.asyncio
async def test_unverified_run_keeps_its_bundle_and_creates_no_output(tmp_path: Path) -> None:
    agent = ScriptedInterviewAgent(
        [AgentDecision(kind="final", output=ungrounded_interview_payload())] * 3
    )
    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key="not-a-real-key"),
        media=FakeInterviewMedia(),
        recognizer=FakeInterviewTranscriber(),
        sampler=AdaptiveSampler(),
        agent_model=agent,
    )
    output_dir = tmp_path / "out"
    run_dir = tmp_path / "runs" / "partial"

    result = await runner.run(_video(tmp_path), output_dir, run_dir=run_dir)

    assert result.terminal_state is TerminalState.PARTIAL
    assert result.run_path == run_dir.resolve()
    assert not output_dir.exists()
    assert _manifest(run_dir)["terminal_state"] == "PARTIAL"


@pytest.mark.asyncio
async def test_blocked_default_stack_keeps_its_bundle_and_identifies_qwen(tmp_path: Path) -> None:
    media = FakeInterviewMedia()
    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key=None), media=media, sampler=AdaptiveSampler()
    )
    run_dir = tmp_path / "runs" / "blocked"

    result = await runner.run(_video(tmp_path), tmp_path / "out", run_dir=run_dir)

    assert result.terminal_state is TerminalState.BLOCKED
    assert result.run_path == run_dir.resolve()
    assert _manifest(run_dir)["terminal_state"] == "BLOCKED"
    header = _run_started(run_dir)
    assert header["provider"] == {"id": "qwen", "model": "qwen3.8-max"}
    assert header["speech_recognizer"] == {"id": "qwen", "model": "qwen-audio-3.1-asr-flash"}
    assert media.audio_calls == []


@pytest.mark.asyncio
async def test_injected_provider_identity_is_recorded(tmp_path: Path) -> None:
    runner = InterviewRecipeRunner(
        media=FakeInterviewMedia(),
        recognizer=FakeInterviewTranscriber(),
        sampler=AdaptiveSampler(),
        provider=MockProvider(),
    )
    run_dir = tmp_path / "runs" / "mock"

    result = await runner.run(_video(tmp_path), tmp_path / "out", run_dir=run_dir)

    assert result.run_path == run_dir.resolve()
    assert _run_started(run_dir)["provider"] == {"id": "mock", "model": "mock"}


@pytest.mark.asyncio
async def test_render_failure_after_a_verified_run_still_reports_the_bundle(
    tmp_path: Path,
) -> None:
    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key="not-a-real-key"),
        media=FakeInterviewMedia(),
        recognizer=FakeInterviewTranscriber(),
        sampler=AdaptiveSampler(),
        agent_model=_succeeding_agent(),
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("user data", encoding="utf-8")
    run_dir = tmp_path / "runs" / "render"

    result = await runner.run(_video(tmp_path), output_dir, run_dir=run_dir)

    assert result.terminal_state is TerminalState.FAILED
    assert result.failure_reason == "unexpected recipe runner error"
    assert result.run_path == run_dir.resolve()
    assert _manifest(run_dir)["terminal_state"] == "SUCCEEDED"
    assert (output_dir / "keep.txt").read_text(encoding="utf-8") == "user data"


@pytest.mark.asyncio
async def test_non_empty_run_dir_is_refused_without_touching_it(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "taken"
    run_dir.mkdir(parents=True)
    (run_dir / "other.txt").write_text("not a bundle", encoding="utf-8")
    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key="not-a-real-key"),
        media=FakeInterviewMedia(),
        recognizer=FakeInterviewTranscriber(),
        sampler=AdaptiveSampler(),
        agent_model=_succeeding_agent(),
    )

    result = await runner.run(_video(tmp_path), tmp_path / "out", run_dir=run_dir)

    assert result.terminal_state is TerminalState.FAILED
    assert result.run_path is None
    assert [entry.name for entry in run_dir.iterdir()] == ["other.txt"]


@pytest.mark.asyncio
async def test_library_default_still_uses_a_private_temporary_bundle(tmp_path: Path) -> None:
    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key="not-a-real-key"),
        media=FakeInterviewMedia(),
        recognizer=FakeInterviewTranscriber(),
        sampler=AdaptiveSampler(),
        agent_model=_succeeding_agent(),
    )

    result = await runner.run(_video(tmp_path), tmp_path / "out")

    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.run_path is None
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["interview.mp4", "out"]
