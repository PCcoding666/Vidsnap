"""Offline end-to-end success contract for the interview recipe runner.

Drives one fully offline, deterministic ``InterviewRecipeRunner.run()`` end to
end through injected fakes for every port (local media, transcription, agent
model) and asserts the truthful terminal contract: a SUCCEEDED run whose six
deterministic verifier gates all pass, exactly the four grounded editorial
artifacts rendered into the output directory, a self-contained ASCII trace with
grounded claim and tool identifiers, bounded default tool schemas plus the
strict interview output schema exposed to every agent decision, and zero use of
direct-baseline timeline extraction or the legacy one-shot planner port.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import JsonValue

from vidsnap.config import HarnessConfig
from vidsnap.contracts import (
    AgentDecision,
    ProviderUsage,
    TerminalState,
    ToolCallRequest,
    VideoGoal,
    VideoSource,
)
from vidsnap.plugins.base import TranscriptionResponse
from vidsnap.providers.base import (
    AgentDecisionResponse,
    AgentStepRequest,
    ToolPlanResponse,
)
from vidsnap.recipes import InterviewRecipeRunner
from vidsnap.video.probe import ExtractedFrame, MediaProbe
from vidsnap.video.sampling import AdaptiveSampler, FrameCandidate

TRANSCRIPT_TEXT = "Host: What changed?\nGuest: The workflow became auditable."
EXPECTED_GATES = frozenset(
    {
        "dialogue_present",
        "dialogue_retained",
        "timestamps_in_bounds",
        "referenced_evidence_exists",
        "source_text_supported",
        "provenance_complete",
    }
)
EXPECTED_TOOL_NAMES = frozenset({"transcribe_audio", "sample_evidence"})
_FRAME_BYTES = b"\xff\xd8\xff\xe0deterministic-frame"
_AUDIO_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt deterministic-audio"


class FakeInterviewMedia:
    """Offline FFmpegPort double that writes tiny deterministic local artifacts."""

    def __init__(self) -> None:
        self.probe_calls = 0
        self.candidate_calls = 0
        self.extract_frames_calls = 0
        self.audio_calls: list[Path] = []
        self.timeline_calls = 0

    async def probe(self, source: Path) -> MediaProbe:
        del source
        self.probe_calls += 1
        return MediaProbe(
            duration_seconds=8.0,
            fps=24.0,
            width=320,
            height=240,
            has_audio=True,
            video_codec="h264",
            audio_codec="aac",
        )

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        del source, probe
        self.candidate_calls += 1
        return [
            FrameCandidate(timestamp=1.5, score=1.0, perceptual_hash="cand-1.5", source="uniform"),
            FrameCandidate(timestamp=5.0, score=1.0, perceptual_hash="cand-5.0", source="scene"),
        ]

    async def extract_frames(
        self,
        source: Path,
        candidates: Sequence[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        del source
        self.extract_frames_calls += 1
        output_dir.mkdir(parents=True, exist_ok=True)
        frames: list[ExtractedFrame] = []
        for index, candidate in enumerate(sorted(candidates, key=lambda item: item.timestamp)):
            frame_path = output_dir / f"frame-{index:03d}-{candidate.timestamp:.3f}.jpg"
            frame_path.write_bytes(_FRAME_BYTES)
            frames.append(
                ExtractedFrame(
                    path=frame_path,
                    timestamp=candidate.timestamp,
                    perceptual_hash=candidate.perceptual_hash,
                )
            )
        return frames

    async def extract_timeline_frames(
        self,
        source: Path,
        *,
        fps: int,
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        """Record any use; the agentic recipe path must never take this branch."""
        del source, fps, output_dir
        self.timeline_calls += 1
        return []

    async def extract_audio(
        self,
        source: Path,
        output_path: Path,
        *,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Path:
        del source, start_seconds, end_seconds
        self.audio_calls.append(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_AUDIO_BYTES)
        return output_path


class FakeInterviewTranscriber:
    """TranscriptionPort double returning the fixed two-turn interview dialogue."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        del mime_type
        self.calls.append(len(audio_bytes))
        return TranscriptionResponse(text=TRANSCRIPT_TEXT)


class ScriptedInterviewAgent:
    """AgentModelPort double replaying one fixed bounded decision script.

    Every AgentStepRequest is recorded verbatim so the test can assert the tool
    schemas and the strict interview output schema each decision observed. The
    legacy one-shot plan_tools port is a tripwire that must never be called.
    """

    def __init__(self, decisions: Sequence[AgentDecision]) -> None:
        self._decisions: deque[AgentDecision] = deque(decisions)
        self.requests: list[AgentStepRequest] = []
        self.plan_tools_calls = 0

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        self.requests.append(request)
        if not self._decisions:
            raise AssertionError("ScriptedInterviewAgent received an unexpected decide_next call")
        return AgentDecisionResponse(
            decision=self._decisions.popleft(),
            usage=ProviderUsage(reported=False),
        )

    async def plan_tools(self, probe: MediaProbe, goal: VideoGoal) -> ToolPlanResponse:
        del probe, goal
        self.plan_tools_calls += 1
        raise AssertionError("agentic interview runs must not call the legacy plan_tools port")


def interview_final_payload() -> dict[str, JsonValue]:
    """One strict InterviewRecipeResult payload grounded in captured evidence."""
    return {
        "segments": [
            {
                "id": "seg-question",
                "kind": "question",
                "speaker": "Host",
                "start_time": 0.0,
                "end_time": 2.0,
                "source_text": "Host: What changed?",
                "rendered_text": "Host: What changed?",
                "source_language": "en",
                "rendered_language": "en",
                "transcript_evidence_id": "transcript-001",
                "editorial_status": "source",
            },
            {
                "id": "seg-answer",
                "kind": "answer",
                "speaker": "Guest",
                "start_time": 4.0,
                "end_time": 6.5,
                "source_text": "Guest: The workflow became auditable.",
                "rendered_text": "Guest: The workflow became auditable.",
                "source_language": "en",
                "rendered_language": "en",
                "transcript_evidence_id": "transcript-001",
                "frame_evidence_id": "frame-001",
                "editorial_status": "source",
            },
        ],
        "blocks": [
            {"id": "block-question", "type": "source", "segment_id": "seg-question"},
            {"id": "block-answer", "type": "source", "segment_id": "seg-answer"},
            {
                "id": "block-commentary",
                "type": "commentary",
                "text": "The guest credits the new workflow with making the results auditable.",
                "evidence_ids": ["transcript-001", "frame-001"],
                "editorial_status": "model_commentary",
            },
        ],
        "brief_points": [
            {
                "id": "brief-1",
                "commentary": "The dialogue records a workflow change that became auditable.",
                "evidence": ["transcript-001", "frame-001"],
                "editorial_status": "model_commentary",
            }
        ],
    }


def ungrounded_interview_payload() -> dict[str, JsonValue]:
    """Schema-valid dialogue grounded in evidence ids that were never captured."""
    return {
        "segments": [
            {
                "id": "seg-question",
                "kind": "question",
                "speaker": "Host",
                "start_time": 0.0,
                "end_time": 2.0,
                "source_text": "Invented dialogue that was never spoken.",
                "rendered_text": "Invented dialogue that was never spoken.",
                "source_language": "en",
                "rendered_language": "en",
                "transcript_evidence_id": "transcript-999",
                "editorial_status": "source",
            },
            {
                "id": "seg-answer",
                "kind": "answer",
                "speaker": "Guest",
                "start_time": 4.0,
                "end_time": 6.5,
                "source_text": "Unrelated fabricated answer text.",
                "rendered_text": "Unrelated fabricated answer text.",
                "source_language": "en",
                "rendered_language": "en",
                "transcript_evidence_id": "transcript-999",
                "frame_evidence_id": "frame-999",
                "editorial_status": "source",
            },
        ],
        "blocks": [
            {"id": "block-question", "type": "source", "segment_id": "seg-question"},
            {"id": "block-answer", "type": "source", "segment_id": "seg-answer"},
        ],
        "brief_points": [],
    }


@pytest.mark.asyncio
async def test_interview_runner_succeeds_offline_through_bounded_agentic_path(
    tmp_path: Path,
) -> None:
    media = FakeInterviewMedia()
    transcriber = FakeInterviewTranscriber()
    agent = ScriptedInterviewAgent(
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
    video_path = tmp_path / "interview.mp4"
    video_path.write_bytes(b"deterministic-local-interview-video-bytes")
    output_dir = tmp_path / "recipe-output"

    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key="not-a-real-key"),
        media=media,
        recognizer=transcriber,
        sampler=AdaptiveSampler(),
        agent_model=agent,
    )
    result = await runner.run(VideoSource(path=video_path), output_dir)

    # Truthful terminal outcome with all six deterministic gates passing.
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert result.failure_reason is None
    assert result.verification is not None
    assert result.verification.passed is True
    assert set(result.verification.gates) == EXPECTED_GATES
    assert all(result.verification.gates.values())

    # Exactly the four grounded editorial artifacts land in the output directory.
    assert result.artifacts is not None
    assert result.artifacts.transcript_path == output_dir / "transcript.zh.md"
    assert result.artifacts.article_path == output_dir / "interview.article.md"
    assert result.artifacts.brief_path == output_dir / "brief.md"
    assert result.artifacts.trace_path == output_dir / "trace.html"
    assert {entry.name for entry in output_dir.iterdir()} == {
        "transcript.zh.md",
        "interview.article.md",
        "brief.md",
        "trace.html",
    }
    for artifact_name in ("transcript.zh.md", "interview.article.md", "brief.md", "trace.html"):
        artifact = output_dir / artifact_name
        assert artifact.is_file() and artifact.stat().st_size > 0

    # The trace export is self-contained offline HTML with ASCII claim/tool IDs.
    trace_html = (output_dir / "trace.html").read_text(encoding="utf-8")
    assert trace_html.isascii()
    assert "http://" not in trace_html and "https://" not in trace_html
    for claim_identifier in ("transcript-001", "frame-001"):
        assert claim_identifier in trace_html
    for tool_identifier in ("transcribe_audio", "sample_evidence"):
        assert tool_identifier in trace_html

    # Every agent decision observed exactly the bounded default tools and the
    # strict interview recipe output schema with recognizable properties.
    assert len(agent.requests) == 3
    for request in agent.requests:
        assert {str(schema["name"]) for schema in request.tool_schemas} == EXPECTED_TOOL_NAMES
        assert all(isinstance(schema["input_schema"], dict) for schema in request.tool_schemas)
        output_schema = request.output_schema
        assert set(output_schema["properties"]) == {"segments", "blocks", "brief_points"}
        assert output_schema["additionalProperties"] is False
        assert "TranscriptSegment" in output_schema["$defs"]

    # The final decision saw exactly the captured evidence its output references.
    final_request = agent.requests[-1]
    assert tuple(item.id for item in final_request.evidence) == ("transcript-001", "frame-001")

    # No real network dependency: only the injected local ports were consulted,
    # and direct-baseline timeline extraction stayed strictly unused.
    assert media.probe_calls == 1
    assert len(media.audio_calls) == 1 and not media.audio_calls[0].is_file()
    assert media.candidate_calls == 1
    assert media.extract_frames_calls == 1
    assert len(transcriber.calls) == 1
    assert agent.plan_tools_calls == 0
    assert media.timeline_calls == 0


@pytest.mark.asyncio
async def test_interview_runner_blocks_without_configured_model_key(tmp_path: Path) -> None:
    media = FakeInterviewMedia()
    transcriber = FakeInterviewTranscriber()
    video_path = tmp_path / "interview.mp4"
    video_path.write_bytes(b"deterministic-local-interview-video-bytes")
    output_dir = tmp_path / "blocked-output"

    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key=None),
        media=media,
        recognizer=transcriber,
        sampler=AdaptiveSampler(),
    )
    result = await runner.run(VideoSource(path=video_path), output_dir)

    assert result.terminal_state is TerminalState.BLOCKED
    assert result.artifacts is None
    assert result.failure_reason == "provider unavailable"
    assert result.verification is None
    assert not output_dir.exists()
    assert media.probe_calls == 1
    assert media.audio_calls == []
    assert media.candidate_calls == 0
    assert media.extract_frames_calls == 0
    result_repr = repr(result)
    for secret_marker in ("api_key", "authorization", "bearer", "qwen_api_key"):
        assert secret_marker not in result_repr.lower()


@pytest.mark.asyncio
async def test_interview_runner_partial_when_final_output_is_ungrounded(tmp_path: Path) -> None:
    media = FakeInterviewMedia()
    transcriber = FakeInterviewTranscriber()
    agent = ScriptedInterviewAgent(
        [
            AgentDecision(kind="final", output=ungrounded_interview_payload()),
            AgentDecision(kind="final", output=ungrounded_interview_payload()),
            AgentDecision(kind="final", output=ungrounded_interview_payload()),
        ]
    )
    video_path = tmp_path / "interview.mp4"
    video_path.write_bytes(b"deterministic-local-interview-video-bytes")
    output_dir = tmp_path / "ungrounded-output"

    runner = InterviewRecipeRunner(
        config=HarnessConfig(api_key="not-a-real-key"),
        media=media,
        recognizer=transcriber,
        sampler=AdaptiveSampler(),
        agent_model=agent,
    )
    result = await runner.run(VideoSource(path=video_path), output_dir)

    assert result.terminal_state is TerminalState.PARTIAL
    assert result.artifacts is None
    assert result.failure_reason is None
    assert result.verification is not None
    assert result.verification.passed is False
    assert result.verification.gates["referenced_evidence_exists"] is False
    assert result.verification.gates["source_text_supported"] is False
    assert not output_dir.exists()
    assert len(agent.requests) == 3
    assert media.probe_calls == 1
    assert media.audio_calls == []
    assert media.candidate_calls == 0
    assert media.extract_frames_calls == 0
    assert media.timeline_calls == 0
    assert agent.plan_tools_calls == 0
