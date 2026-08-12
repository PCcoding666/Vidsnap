"""Three-path formal benchmark engine behavior with local fake ports."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import (
    BenchmarkProviderConfig,
    FormalBenchmarkEngine,
    MCQModelResponse,
    QwenFormalClient,
    UnsupportedVideoInput,
)
from vidsnap.config import TOKEN_PLAN_BASE_URL
from vidsnap.contracts import ToolPlan, VideoGoal
from vidsnap.providers.base import ToolPlanResponse
from vidsnap.video.probe import ExtractedFrame, FFmpegError, MediaProbe
from vidsnap.video.sampling import FrameCandidate


class FakeFormalMedia:
    def __init__(self) -> None:
        self.visual_candidate_calls = 0
        self.extracted_timestamps: list[float] = []
        self.timeline_calls = 0

    async def probe(self, source: Path) -> MediaProbe:
        assert source.is_file()
        return MediaProbe(2, 24, 640, 360, True)

    async def visual_candidates(self, source: Path, probe: MediaProbe) -> list[FrameCandidate]:
        del source, probe
        self.visual_candidate_calls += 1
        return [
            FrameCandidate(timestamp=0.25, score=1, perceptual_hash="first"),
            FrameCandidate(timestamp=1.75, score=1, perceptual_hash="last"),
        ]

    async def extract_frames(
        self,
        source: Path,
        candidates: list[FrameCandidate],
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        del source
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for index, candidate in enumerate(candidates):
            self.extracted_timestamps.append(candidate.timestamp)
            path = output_dir / f"{index}.jpg"
            path.write_bytes(b"frame")
            frames.append(ExtractedFrame(path, candidate.timestamp, candidate.perceptual_hash))
        return frames

    async def extract_timeline_frames(
        self,
        source: Path,
        *,
        fps: int,
        output_dir: Path,
    ) -> list[ExtractedFrame]:
        self.timeline_calls += 1
        probe = await self.probe(source)
        candidates = [
            FrameCandidate(
                timestamp=index / fps,
                score=1,
                perceptual_hash=f"direct-{index}",
            )
            for index in range(__import__("math").ceil(probe.duration_seconds * fps))
        ]
        return await self.extract_frames(source, candidates, output_dir)

    async def extract_audio(self, source: Path, output_path: Path) -> Path:
        del source
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"audio")
        return output_path


class FakeFormalModel:
    def __init__(self, plan: ToolPlan) -> None:
        self.plan = plan
        self.plan_calls = 0
        self.answer_calls = 0

    async def plan_tools(self, probe: MediaProbe, goal) -> ToolPlanResponse:
        del probe, goal
        self.plan_calls += 1
        return ToolPlanResponse(
            plan=self.plan,
            input_tokens=5,
            output_tokens=2,
            input_bytes=50,
        )

    async def transcribe_audio(self, audio_bytes: bytes) -> MCQModelResponse:
        assert audio_bytes == b"audio"
        return MCQModelResponse(
            text="spoken words",
            input_tokens=7,
            output_tokens=3,
            input_bytes=75,
        )

    async def answer_mcq(
        self,
        case: FormalCase,
        *,
        frames: tuple[ExtractedFrame, ...],
        transcript: str | None,
        video_path: Path | None,
        frame_sequence_fps: int | None = None,
    ) -> MCQModelResponse:
        del case, frames, transcript, video_path, frame_sequence_fps
        self.answer_calls += 1
        return MCQModelResponse(
            text="The best answer is: A.",
            input_tokens=13,
            output_tokens=1,
            input_bytes=100,
        )


class FailingPlanModel(FakeFormalModel):
    async def plan_tools(self, probe: MediaProbe, goal) -> ToolPlanResponse:
        del probe, goal
        from vidsnap.providers.base import ProviderError

        raise ProviderError("safe planner failure")


def make_case(tmp_path: Path, *, subtitle: bool = True) -> FormalCase:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    subtitle_path = tmp_path / "subtitle.txt" if subtitle else None
    if subtitle_path is not None:
        subtitle_path.write_text("spoken words")
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
        subtitle_path=subtitle_path,
        has_audio=True,
        duration_stratum="short",
        requirements=("speech",),
        expected_tools=("transcribe_audio",),
        tool_annotation_reason="speech-required",
    )


@pytest.mark.asyncio
async def test_agentic_path_runs_only_selected_audio_tool_and_accounts_usage(tmp_path) -> None:
    """An unselected visual call or missing planner usage must fail this test."""
    media = FakeFormalMedia()
    model = FakeFormalModel(ToolPlan(tools=("transcribe_audio",)))

    outcome = await FormalBenchmarkEngine(media=media, model=model).run_case(
        make_case(tmp_path),
        variant="agentic",
        work_dir=tmp_path / "agentic",
        direct_input_mode="frames_2fps",
    )

    assert outcome.answer == "A"
    assert outcome.correct is True
    assert outcome.selected_tools == ("transcribe_audio",)
    assert outcome.usage.model_calls == 2
    assert outcome.usage.input_tokens == 18
    assert outcome.usage.output_tokens == 3
    assert outcome.usage.input_bytes == 150
    assert outcome.usage.evidence_frames == 0
    assert outcome.verifier_passed is True
    assert media.visual_candidate_calls == 0


@pytest.mark.asyncio
async def test_agentic_failed_planner_attempt_is_counted(tmp_path) -> None:
    """A failed provider attempt must not disappear from model-call accounting."""
    outcome = await FormalBenchmarkEngine(
        media=FakeFormalMedia(),
        model=FailingPlanModel(ToolPlan(tools=())),
    ).run_case(
        make_case(tmp_path),
        variant="agentic",
        work_dir=tmp_path / "failed-plan",
        direct_input_mode="frames_2fps",
    )

    assert outcome.terminal_state.value == "FAILED"
    assert outcome.usage.model_calls == 1


@pytest.mark.asyncio
async def test_fixed_path_keeps_both_acquisition_tools_without_planner(tmp_path) -> None:
    """Planner control or omitted visual acquisition in fixed mode must fail this test."""
    media = FakeFormalMedia()
    model = FakeFormalModel(ToolPlan(tools=()))

    outcome = await FormalBenchmarkEngine(media=media, model=model).run_case(
        make_case(tmp_path),
        variant="fixed",
        work_dir=tmp_path / "fixed",
        direct_input_mode="frames_2fps",
    )

    assert outcome.selected_tools == ("transcribe_audio", "sample_evidence")
    assert outcome.usage.model_calls == 1
    assert outcome.usage.evidence_frames == 2
    assert model.plan_calls == 0
    assert media.visual_candidate_calls == 1


@pytest.mark.asyncio
async def test_direct_frame_fallback_covers_complete_timeline_at_two_fps(tmp_path) -> None:
    """Sparse or adaptive Direct fallback frames must fail this test."""
    media = FakeFormalMedia()
    model = FakeFormalModel(ToolPlan(tools=()))

    outcome = await FormalBenchmarkEngine(media=media, model=model).run_case(
        make_case(tmp_path),
        variant="direct",
        work_dir=tmp_path / "direct",
        direct_input_mode="frames_2fps",
    )

    assert media.extracted_timestamps == [0.0, 0.5, 1.0, 1.5]
    assert media.timeline_calls == 1
    assert outcome.usage.evidence_frames == 4
    assert outcome.direct_input_mode == "frames_2fps"


@pytest.mark.asyncio
async def test_direct_fallback_uses_registered_video_frame_list_wire_shape(tmp_path) -> None:
    """Thousands of standalone image parts must not replace the official video frame list."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "A"}}]})

    frame_paths = []
    for index in range(4):
        frame = tmp_path / f"frame-{index}.jpg"
        frame.write_bytes(b"jpeg")
        frame_paths.append(ExtractedFrame(frame, index / 2, f"hash-{index}"))
    client = QwenFormalClient(
        BenchmarkProviderConfig(api_key="test", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    )

    await client.answer_mcq(
        make_case(tmp_path),
        frames=tuple(frame_paths),
        transcript=None,
        video_path=None,
        frame_sequence_fps=2,
    )

    content = captured["payload"]["messages"][1]["content"]
    assert len(content) == 2
    assert content[1]["type"] == "video"
    assert content[1]["fps"] == 2
    assert len(content[1]["video"]) == 4


@pytest.mark.asyncio
async def test_formal_qwen_client_uses_only_fixed_model_for_mcq(tmp_path) -> None:
    """A caller-selected model or non-image evidence payload must fail this test."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "A"}}],
                "usage": {"prompt_tokens": 23, "completion_tokens": 1},
            },
        )

    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"jpeg-bytes")
    client = QwenFormalClient(
        BenchmarkProviderConfig(api_key="test", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    )

    response = await client.answer_mcq(
        make_case(tmp_path),
        frames=(ExtractedFrame(frame_path, 0.5, "hash"),),
        transcript="spoken words",
        video_path=None,
    )

    payload = captured["payload"]
    assert payload["model"] == "qwen3.8-max"
    assert payload["messages"][1]["content"][1]["type"] == "image_url"
    assert response.text == "A"
    assert response.input_tokens == 23
    assert response.output_tokens == 1
    assert response.input_bytes > len(b"jpeg-bytes")


@pytest.mark.asyncio
async def test_formal_qwen_client_classifies_rejected_complete_video(tmp_path) -> None:
    """A rejected complete-video request must trigger the registered fallback signal."""

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(415, json={"error": "unsupported media"})

    client = QwenFormalClient(
        BenchmarkProviderConfig(api_key="test", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(UnsupportedVideoInput) as captured:
        await client.answer_mcq(
            make_case(tmp_path),
            frames=(),
            transcript=None,
            video_path=tmp_path / "video.mp4",
        )
    assert captured.value.input_bytes > len(b"video")


@pytest.mark.asyncio
async def test_failed_provider_request_retains_attempted_call_and_bytes(tmp_path) -> None:
    """Rejected payload cost must not be reported as zero evidence input."""

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500, json={"error": "provider failure"})

    outcome = await FormalBenchmarkEngine(
        media=FakeFormalMedia(),
        model=QwenFormalClient(
            BenchmarkProviderConfig(api_key="test", base_url=TOKEN_PLAN_BASE_URL),
            transport=httpx.MockTransport(handler),
        ),
    ).run_case(
        make_case(tmp_path),
        variant="direct",
        work_dir=tmp_path / "failed-request",
        direct_input_mode="video",
    )

    assert outcome.terminal_state.value == "FAILED"
    assert outcome.usage.model_calls == 1
    assert outcome.usage.input_bytes > len(b"video")


@pytest.mark.asyncio
async def test_formal_qwen_client_uses_qwen_max_for_audio_transcription() -> None:
    """Falling back to a different ASR model must fail this test."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    client = QwenFormalClient(
        BenchmarkProviderConfig(api_key="test", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    )

    response = await client.transcribe_audio(b"audio")

    payload = captured["payload"]
    assert payload["model"] == "qwen3.8-max"
    assert payload["messages"][1]["content"][0]["type"] == "input_audio"
    assert response.text == "hello"


@pytest.mark.asyncio
async def test_formal_qwen_client_planner_rejects_broader_tool_surface() -> None:
    """Changing the registered planner tools or model must fail this test."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"tools":["sample_evidence"]}'}}]},
        )

    client = QwenFormalClient(
        BenchmarkProviderConfig(api_key="test", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    )
    response = await client.plan_tools(
        MediaProbe(2, 24, 640, 360, True),
        VideoGoal(objective="What happens?"),
    )

    payload = captured["payload"]
    assert payload["model"] == "qwen3.8-max"
    assert response.plan.tools == ("sample_evidence",)


@pytest.mark.asyncio
async def test_formal_qwen_client_normalizes_exact_named_tool_objects() -> None:
    """Qwen's bounded named-tool wire shape must map to the strict internal plan."""

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"tools":[{"name":"transcribe_audio"},{"name":"sample_evidence"}]}'
                            )
                        }
                    }
                ]
            },
        )

    client = QwenFormalClient(
        BenchmarkProviderConfig(api_key="test", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    )
    response = await client.plan_tools(
        MediaProbe(2, 24, 640, 360, True),
        VideoGoal(objective="What happens?"),
    )

    assert response.plan.tools == ("transcribe_audio", "sample_evidence")


@pytest.mark.asyncio
async def test_formal_engine_records_local_media_failure_as_typed_outcome(tmp_path) -> None:
    """Leaking an FFmpeg exception past the per-case boundary must fail this test."""

    class BrokenMedia(FakeFormalMedia):
        async def probe(self, source: Path) -> MediaProbe:
            del source
            raise FFmpegError("local decode failed")

    outcome = await FormalBenchmarkEngine(
        media=BrokenMedia(),
        model=FakeFormalModel(ToolPlan(tools=())),
    ).run_case(
        make_case(tmp_path),
        variant="fixed",
        work_dir=tmp_path / "broken",
        direct_input_mode="frames_2fps",
    )

    assert outcome.terminal_state.value == "FAILED"
    assert outcome.failure_reason == "benchmark case failed"
