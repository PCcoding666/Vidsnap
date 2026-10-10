"""The interview recipe's default speech recognizer gets the ASR key and timeout."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_interview_runner import (
    FakeInterviewMedia,
    ScriptedInterviewAgent,
    ungrounded_interview_payload,
)

from vidsnap.config import HarnessConfig
from vidsnap.contracts import AgentDecision, VideoSource
from vidsnap.recipes import InterviewRecipeRunner
from vidsnap.recipes import runner as runner_module
from vidsnap.video.sampling import AdaptiveSampler


class _SpyRecognizer:
    constructed: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        type(self).constructed.append(kwargs)

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/wav") -> str:
        return ""


@pytest.mark.asyncio
async def test_default_recognizer_is_built_with_the_asr_key_and_request_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _SpyRecognizer.constructed = []
    monkeypatch.setattr(runner_module, "QwenAsrRecognizer", _SpyRecognizer)
    video = tmp_path / "interview.mp4"
    video.write_bytes(b"deterministic-local-interview-video-bytes")
    runner = InterviewRecipeRunner(
        config=HarnessConfig(
            api_key="text-credential-for-tests",
            asr_api_key="asr-credential-for-tests",
            request_timeout_seconds=77.0,
        ),
        media=FakeInterviewMedia(),
        sampler=AdaptiveSampler(),
        agent_model=ScriptedInterviewAgent(
            [AgentDecision(kind="final", output=ungrounded_interview_payload())] * 3
        ),
    )

    await runner.run(VideoSource(path=video), tmp_path / "out")

    assert _SpyRecognizer.constructed == [
        {"api_key": "asr-credential-for-tests", "timeout_seconds": 77.0}
    ]
