"""RED tests for Task 9: benchmark task adapters on top of the harness kernel.

These tests fail at import until `vidsnap.benchmark.adapters` exists with
`MCQTaskAdapter`, `FormalTranscriptionAdapter`, and the strict `MCQResult`
contract, and until `ProviderUsage` plus `EventUsage` can represent
`model_calls` additively.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from vidsnap.benchmark.adapters import (
    FormalTranscriptionAdapter,
    MCQResult,
    MCQTaskAdapter,
)
from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import MCQModelResponse
from vidsnap.contracts import Evidence, VideoGoal
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.loopspec import default_loop_spec
from vidsnap.contracts.models import TerminalState
from vidsnap.loop.events import EventUsage
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.plugins.base import TranscriptionResponse
from vidsnap.video.probe import ExtractedFrame, MediaProbe


def make_case(tmp_path: Path) -> FormalCase:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    return FormalCase(
        case_id="case-1",
        dataset="Video-MME",
        dataset_version="revision",
        dataset_license="Academic research only.",
        source_url="https://github.com/MME-Benchmarks/Video-MME",
        source=video,
        source_sha256="a" * 64,
        task_family="Information Synopsis",
        question="What happens?",
        options={"A": "One event", "B": "Another event"},
        answer="A",
        subtitle_path=None,
        has_audio=True,
        duration_stratum="short",
        requirements=("speech",),
        expected_tools=("transcribe_audio",),
        tool_annotation_reason="speech-required",
    )


def make_probe() -> MediaProbe:
    return MediaProbe(duration_seconds=2.0, fps=24.0, width=640, height=360, has_audio=True)


class RecordingFormalModel:
    """A fake FormalModelPort that captures inputs and reports real counters."""

    def __init__(self, *, answer_text: str = "The best answer is: A.") -> None:
        self.answer_text = answer_text
        self.answer_calls: list[dict[str, object]] = []
        self.transcribe_calls: list[bytes] = []

    async def answer_mcq(
        self,
        case: FormalCase,
        *,
        frames: tuple[ExtractedFrame, ...],
        transcript: str | None,
        video_path: Path | None,
        frame_sequence_fps: int | None = None,
    ) -> MCQModelResponse:
        self.answer_calls.append(
            {
                "case": case,
                "frames": frames,
                "transcript": transcript,
                "video_path": video_path,
                "frame_sequence_fps": frame_sequence_fps,
            }
        )
        return MCQModelResponse(
            self.answer_text,
            input_tokens=13,
            output_tokens=1,
            input_bytes=100,
            usage_reported=True,
        )

    async def transcribe_audio(self, audio_bytes: bytes) -> MCQModelResponse:
        self.transcribe_calls.append(audio_bytes)
        return MCQModelResponse(
            "spoken words",
            input_tokens=7,
            output_tokens=3,
            input_bytes=75,
            usage_reported=True,
        )


def make_evidence(tmp_path: Path) -> tuple[Evidence, Evidence]:
    frame_path = tmp_path / "frame-1.jpg"
    frame_path.write_bytes(b"frame")
    return (
        Evidence(
            id="frame-1",
            start_seconds=0.5,
            end_seconds=0.5,
            modality="frame",
            artifact_path=frame_path,
        ),
        Evidence(
            id="transcript-1",
            start_seconds=0.0,
            end_seconds=2.0,
            modality="transcript",
            content="spoken words",
        ),
    )


@pytest.mark.asyncio
async def test_mcq_adapter_converts_evidence_and_maps_reported_usage(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    adapter = MCQTaskAdapter(case)
    assert isinstance(adapter.goal, VideoGoal)
    assert adapter.output_model is MCQResult

    model = RecordingFormalModel()
    result, usage = await adapter.request_final(model, make_evidence(tmp_path), make_probe())

    assert len(model.answer_calls) == 1
    call = model.answer_calls[0]
    assert call["case"] is case
    frames = call["frames"]
    assert isinstance(frames, tuple) and len(frames) == 1
    assert frames[0].path == tmp_path / "frame-1.jpg"
    assert frames[0].timestamp == 0.5
    assert call["transcript"] == "spoken words"
    assert call["video_path"] is None

    assert isinstance(result, MCQResult)
    assert result.answer == "A"

    assert usage.model_calls == 1
    assert usage.input_bytes == 100
    assert usage.input_tokens == 13
    assert usage.output_tokens == 1
    assert usage.reported is True


@pytest.mark.asyncio
async def test_mcq_adapter_parses_only_through_parse_mcq_answer(tmp_path: Path) -> None:
    adapter = MCQTaskAdapter(make_case(tmp_path))
    model = RecordingFormalModel(answer_text="C")
    with pytest.raises(ValueError):
        await adapter.request_final(model, make_evidence(tmp_path), make_probe())


def test_parse_final_accepts_only_declared_answer_payload(tmp_path: Path) -> None:
    adapter = MCQTaskAdapter(make_case(tmp_path))

    assert adapter.parse_final({"answer": "A"}) == MCQResult(answer="A")

    with pytest.raises(ValueError):
        adapter.parse_final({"answer": "Z"})
    with pytest.raises(ValueError):
        adapter.parse_final({"answer": "A", "confidence": 0.9})
    with pytest.raises(ValueError):
        adapter.parse_final({})


def test_verify_reproduces_five_deterministic_gates(tmp_path: Path) -> None:
    adapter = MCQTaskAdapter(make_case(tmp_path))
    probe = make_probe()

    good = adapter.verify(MCQResult(answer="A"), make_evidence(tmp_path), probe)
    assert good.passed is True
    assert good.gates == {
        "schema_valid": True,
        "timestamps_in_bounds": True,
        "referenced_evidence_exists": True,
        "claims_are_supported": True,
        "required_sections_covered": True,
    }

    missing = adapter.verify(MCQResult(answer="A"), (), probe)
    assert missing.passed is False
    assert missing.gates == {
        "schema_valid": True,
        "timestamps_in_bounds": True,
        "referenced_evidence_exists": False,
        "claims_are_supported": False,
        "required_sections_covered": True,
    }


@pytest.mark.asyncio
async def test_transcription_adapter_reports_one_model_call_without_raw_logging(
    tmp_path: Path,
) -> None:
    model = RecordingFormalModel()
    adapter = FormalTranscriptionAdapter(model)

    response = await adapter.transcribe(b"audio")

    assert isinstance(response, TranscriptionResponse)
    assert {field.name for field in dataclasses.fields(response)} == {"text", "usage"}
    assert response.text == "spoken words"
    assert model.transcribe_calls == [b"audio"]
    assert response.usage.model_calls == 1
    assert response.usage.input_bytes == 75
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 3
    assert response.usage.reported is True


@pytest.mark.asyncio
async def test_transcription_adapter_returns_pre_existing_subtitle_without_model_call() -> None:
    model = RecordingFormalModel()
    adapter = FormalTranscriptionAdapter(model, subtitle_text="spoken words")

    response = await adapter.transcribe(b"audio")

    assert response.text == "spoken words"
    assert model.transcribe_calls == []
    assert response.usage.model_calls == 0


def test_usage_contracts_represent_model_calls_additively() -> None:
    provider_total = ProviderUsage(
        model_calls=1,
        input_bytes=10,
        input_tokens=2,
        output_tokens=1,
        reported=True,
    ) + ProviderUsage(
        model_calls=2,
        input_bytes=5,
        input_tokens=3,
        output_tokens=4,
        reported=True,
    )
    assert provider_total.model_calls == 3
    assert provider_total.input_bytes == 15
    assert provider_total.input_tokens == 5
    assert provider_total.output_tokens == 5
    assert provider_total.reported is True

    partial = ProviderUsage(model_calls=1, reported=False) + ProviderUsage(
        model_calls=1,
        reported=True,
    )
    assert partial.model_calls == 2
    assert partial.reported is False

    event_total = EventUsage(model_calls=1, tool_calls=2) + EventUsage(
        model_calls=2,
        evidence_frames=1,
    )
    assert event_total.model_calls == 3
    assert event_total.tool_calls == 2
    assert event_total.evidence_frames == 1


def test_run_bundle_accepts_strict_mcq_result_and_hashes_before_finalize(
    tmp_path: Path,
) -> None:
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://example.invalid/v1",
    )

    result_path = bundle.write_result(MCQResult(answer="A"))
    assert json.loads(result_path.read_text(encoding="utf-8")) == {"answer": "A"}
    expected_sha256 = hashlib.sha256(result_path.read_bytes()).hexdigest()

    bundle.finalize(TerminalState.SUCCEEDED)

    manifest = json.loads((bundle.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["result.json"]["sha256"] == expected_sha256
