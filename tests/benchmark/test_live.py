"""Three-path formal benchmark engine behavior with local fake ports."""

from __future__ import annotations

import base64
import inspect
import json
from pathlib import Path

import httpx
import pytest

from vidsnap.benchmark.adapters import MCQResult
from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import (
    BenchmarkProviderConfig,
    FormalBenchmarkEngine,
    MCQModelResponse,
    MeasuredProviderError,
    QwenFormalClient,
    UnsupportedVideoInput,
    VariantOutcome,
)
from vidsnap.config import TOKEN_PLAN_BASE_URL
from vidsnap.contracts import Evidence, ToolPlan, VideoGoal
from vidsnap.contracts.agent import AgentDecision, ProviderUsage, ToolCallRequest
from vidsnap.providers.base import (
    AgentDecisionFormatError,
    AgentDecisionResponse,
    AgentStepRequest,
    ToolPlanResponse,
)
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

    async def extract_audio(
        self,
        source: Path,
        output_path: Path,
        *,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Path:
        del source, start_seconds, end_seconds
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"audio")
        return output_path


class FakeFormalModel:
    def __init__(self, plan: ToolPlan) -> None:
        self.plan = plan
        self.plan_calls = 0
        self.answer_calls = 0
        self.decision_calls = 0

    async def plan_tools(self, probe: MediaProbe, goal) -> ToolPlanResponse:
        del probe, goal
        self.plan_calls += 1
        return ToolPlanResponse(
            plan=self.plan,
            input_tokens=5,
            output_tokens=2,
            input_bytes=50,
        )

    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        self.decision_calls += 1
        called = [str(summary["tool"]) for summary in request.tool_results]
        for name in self.plan.tools:
            if name not in called:
                return AgentDecisionResponse(
                    decision=AgentDecision(
                        kind="tool_calls",
                        calls=(
                            ToolCallRequest(
                                name=name,
                                arguments={"max_frames": 2} if name == "sample_evidence" else {},
                            ),
                        ),
                    ),
                    usage=ProviderUsage(input_tokens=6, output_tokens=2, input_bytes=60),
                )
        return AgentDecisionResponse(
            decision=AgentDecision(kind="final", output={"answer": "A"}),
            usage=ProviderUsage(input_tokens=9, output_tokens=1, input_bytes=80),
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


class FailingDecisionModel(FakeFormalModel):
    async def decide_next(self, request: AgentStepRequest) -> AgentDecisionResponse:
        del request
        self.decision_calls += 1
        raise MeasuredProviderError("safe decision failure", input_bytes=55)


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
    assert outcome.usage.input_tokens == 15
    assert outcome.usage.output_tokens == 3
    assert outcome.usage.input_bytes == 140
    assert outcome.usage.evidence_frames == 0
    assert outcome.verifier_passed is True
    assert media.visual_candidate_calls == 0


@pytest.mark.asyncio
async def test_agentic_failed_decision_attempt_is_counted(tmp_path) -> None:
    """A failed provider attempt must not disappear from model-call accounting."""
    outcome = await FormalBenchmarkEngine(
        media=FakeFormalMedia(),
        model=FailingDecisionModel(ToolPlan(tools=())),
    ).run_case(
        make_case(tmp_path),
        variant="agentic",
        work_dir=tmp_path / "failed-decision",
        direct_input_mode="frames_2fps",
    )

    assert outcome.terminal_state.value == "FAILED"
    assert outcome.usage.model_calls == 1
    assert outcome.usage.input_bytes == 55


def read_events(run_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_path / "events.jsonl").read_text().splitlines()]


@pytest.mark.asyncio
async def test_all_benchmark_variants_emit_finalized_kernel_runbundles(tmp_path) -> None:
    """Bypassing the kernel or writing no RunBundle ledger must fail this test."""
    case = make_case(tmp_path)
    media = FakeFormalMedia()
    model = FakeFormalModel(ToolPlan(tools=("transcribe_audio",)))
    engine = FormalBenchmarkEngine(media=media, model=model)

    outcomes: dict[str, VariantOutcome] = {}
    for variant in ("direct", "fixed", "agentic"):
        outcomes[variant] = await engine.run_case(
            case,
            variant=variant,
            work_dir=tmp_path / variant,
            direct_input_mode="frames_2fps",
        )

    sequences: dict[str, tuple[object, ...]] = {}
    for variant in ("direct", "fixed", "agentic"):
        run_path = tmp_path / variant / "run"
        manifest = json.loads((run_path / "manifest.json").read_text())
        assert manifest["terminal_state"] == "SUCCEEDED"
        assert manifest["finalized_at"] is not None

        events = read_events(run_path)
        assert events, "each variant must record a non-empty typed event ledger"
        assert events[0]["event_type"] == "run.started"
        assert events[-1]["event_type"] == "run.completed"
        sequences[variant] = tuple(event["event_type"] for event in events)

        outcome = outcomes[variant]
        assert outcome.case_id == case.case_id
        assert outcome.variant == variant
        assert outcome.terminal_state.value == "SUCCEEDED"
        assert outcome.answer == "A"
        assert outcome.correct is True
        assert outcome.verifier_passed is True
        assert outcome.failure_reason is None

    assert model.plan_calls == 0, "agentic must never fall back to the legacy plan_tools port"

    assert outcomes["direct"].direct_input_mode == "frames_2fps"
    assert outcomes["fixed"].direct_input_mode is None
    assert outcomes["agentic"].direct_input_mode is None
    assert outcomes["direct"].selected_tools == ()
    assert outcomes["fixed"].selected_tools == ("transcribe_audio", "sample_evidence")
    assert outcomes["agentic"].selected_tools == ("transcribe_audio",)

    assert len(set(sequences.values())) == 3, (
        "each variant must keep its own truthful event sequence"
    )


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
async def test_direct_variant_rejects_retired_complete_video_mode(tmp_path) -> None:
    """Claiming complete-video input while frames were used must fail this test."""
    engine = FormalBenchmarkEngine(
        media=FakeFormalMedia(),
        model=FakeFormalModel(ToolPlan(tools=())),
    )

    with pytest.raises(ValueError, match="frames_2fps"):
        await engine.run_case(
            make_case(tmp_path),
            variant="direct",
            work_dir=tmp_path / "direct-video",
            direct_input_mode="video",
        )


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
    assert content[1]["min_pixels"] == 4096
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
    assert response.usage_reported is True


@pytest.mark.asyncio
async def test_formal_qwen_client_mcq_usage_reported_only_when_provider_reports(
    tmp_path,
) -> None:
    """Missing or empty provider usage must never be claimed as reported."""
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"jpeg-bytes")

    async def handler_without_usage(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"choices": [{"message": {"content": "A"}}]})

    response = await make_formal_client(handler_without_usage).answer_mcq(
        make_case(tmp_path),
        frames=(ExtractedFrame(frame_path, 0.5, "hash"),),
        transcript=None,
        video_path=None,
    )
    assert response.usage_reported is False
    assert response.input_bytes > 0
    assert response.input_tokens == 0
    assert response.output_tokens == 0

    async def handler_with_empty_usage(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "A"}}], "usage": {}},
        )

    response = await make_formal_client(handler_with_empty_usage).answer_mcq(
        make_case(tmp_path),
        frames=(ExtractedFrame(frame_path, 0.5, "hash"),),
        transcript=None,
        video_path=None,
    )
    assert response.usage_reported is False
    assert response.input_bytes > 0
    assert response.input_tokens == 0
    assert response.output_tokens == 0


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
        direct_input_mode="frames_2fps",
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
    assert response.usage_reported is False
    assert response.input_bytes > 0
    assert response.input_tokens == 0
    assert response.output_tokens == 0

    async def handler_with_usage(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            },
        )

    reported_response = await make_formal_client(handler_with_usage).transcribe_audio(b"audio")
    assert reported_response.usage_reported is True
    assert reported_response.input_tokens == 11
    assert reported_response.output_tokens == 4

    async def handler_with_empty_usage(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "hello"}}], "usage": {}},
        )

    empty_response = await make_formal_client(handler_with_empty_usage).transcribe_audio(b"audio")
    assert empty_response.usage_reported is False
    assert empty_response.input_bytes > 0
    assert empty_response.input_tokens == 0
    assert empty_response.output_tokens == 0


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


def make_mcq_step_request(
    *,
    evidence: tuple[Evidence, ...] = (),
    tool_results: tuple[dict[str, object], ...] = (),
    remaining_model_calls: int = 12,
    remaining_tool_calls: int = 6,
    remaining_frames: int = 96,
) -> AgentStepRequest:
    return AgentStepRequest(
        goal=VideoGoal(
            objective=json.dumps(
                {
                    "question": "What happens?",
                    "options": {"A": "One event", "B": "Another event"},
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        ),
        probe=MediaProbe(2, 24, 640, 360, True),
        evidence=evidence,
        tool_results=tool_results,
        tool_schemas=(
            {"name": "transcribe_audio", "input_schema": {"type": "object"}},
            {"name": "sample_evidence", "input_schema": {"type": "object"}},
        ),
        output_schema=MCQResult.model_json_schema(),
        remaining_model_calls=remaining_model_calls,
        remaining_tool_calls=remaining_tool_calls,
        remaining_frames=remaining_frames,
    )


def planner_input_from(captured: dict[str, object]) -> dict[str, object]:
    content = captured["payload"]["messages"][1]["content"]
    if isinstance(content, list):
        content = content[0]["text"]
    return json.loads(content)


def make_formal_client(handler) -> QwenFormalClient:
    return QwenFormalClient(
        BenchmarkProviderConfig(api_key="test", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    )


def final_answer_response(answer: str = "A", *, usage: bool = True) -> httpx.Response:
    payload: dict[str, object] = {
        "choices": [
            {"message": {"content": json.dumps({"kind": "final", "output": {"answer": answer}})}}
        ]
    }
    if usage:
        payload["usage"] = {"prompt_tokens": 23, "completion_tokens": 1}
    return httpx.Response(200, json=payload)


@pytest.mark.asyncio
async def test_formal_decide_next_sends_fixed_model_endpoint_and_harness_state_only() -> None:
    """A caller-supplied URL, model, prompt, or budget must fail this test."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return final_answer_response()

    with pytest.raises(ValueError):
        BenchmarkProviderConfig(api_key="test", base_url="https://other.example/v1")
    assert list(inspect.signature(QwenFormalClient.decide_next).parameters) == [
        "self",
        "request",
    ]

    transcript = Evidence(
        id="transcript-1",
        start_seconds=0.0,
        end_seconds=2.0,
        modality="transcript",
        content="spoken words",
    )
    response = await make_formal_client(handler).decide_next(
        make_mcq_step_request(
            evidence=(transcript,),
            tool_results=({"tool": "transcribe_audio", "status": "completed"},),
        )
    )

    assert captured["url"] == f"{TOKEN_PLAN_BASE_URL}/chat/completions"
    assert captured["payload"]["model"] == "qwen3.8-max"
    planner_input = planner_input_from(captured)
    assert planner_input["option_labels"] == ["A", "B"], (
        "declared MCQ option labels must be derived from the registered goal"
    )
    assert planner_input["output_schema"] == MCQResult.model_json_schema()
    assert planner_input["tool_schemas"] == [
        {"name": "transcribe_audio", "input_schema": {"type": "object"}},
        {"name": "sample_evidence", "input_schema": {"type": "object"}},
    ]
    assert planner_input["budgets"] == {
        "remaining_model_calls": 12,
        "remaining_tool_calls": 6,
        "remaining_frames": 96,
    }
    assert planner_input["tool_results"] == [{"tool": "transcribe_audio", "status": "completed"}]
    assert planner_input["evidence"][0]["id"] == "transcript-1"
    assert planner_input["evidence"][0]["content"] == "spoken words"
    assert "artifact_path" not in planner_input["evidence"][0]

    assert isinstance(response, AgentDecisionResponse)
    assert response.decision.kind == "final"
    assert response.decision.output == {"answer": "A"}
    assert response.usage.model_calls == 1
    assert response.usage.input_tokens == 23
    assert response.usage.output_tokens == 1
    assert response.usage.input_bytes > 0
    assert response.usage.reported is True


@pytest.mark.asyncio
async def test_formal_decide_next_parses_strict_tool_calls_with_measured_usage() -> None:
    """A loose tool-call shape or unmeasured usage must fail this test."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "kind": "tool_calls",
                                    "calls": [
                                        {
                                            "name": "sample_evidence",
                                            "arguments": {"max_frames": 4},
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    response = await make_formal_client(handler).decide_next(make_mcq_step_request())

    assert response.decision.kind == "tool_calls"
    assert response.decision.calls == (
        ToolCallRequest(name="sample_evidence", arguments={"max_frames": 4}),
    )
    assert response.usage.model_calls == 1
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 3
    assert response.usage.input_bytes > 0
    assert response.usage.reported is True


@pytest.mark.asyncio
async def test_formal_decide_next_missing_usage_is_unreported_but_still_measured() -> None:
    """Silently reporting absent provider usage as measured zero must fail this test."""

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return final_answer_response(usage=False)

    response = await make_formal_client(handler).decide_next(make_mcq_step_request())

    assert response.usage.reported is False
    assert response.usage.model_calls == 1
    assert response.usage.input_bytes > 0
    assert response.usage.input_tokens == 0
    assert response.usage.output_tokens == 0


@pytest.mark.asyncio
async def test_formal_decide_next_emits_image_data_only_for_supplied_frame_evidence(
    tmp_path,
) -> None:
    """Image bytes for non-frame evidence or missing frames must fail this test."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return final_answer_response()

    client = make_formal_client(handler)
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"jpeg-bytes")
    frame = Evidence(
        id="frame-1",
        start_seconds=0.5,
        end_seconds=0.5,
        modality="frame",
        artifact_path=frame_path,
    )

    await client.decide_next(make_mcq_step_request(evidence=(frame,)))
    content = captured["payload"]["messages"][1]["content"]
    assert isinstance(content, list)
    image_parts = [part for part in content if part["type"] == "image_url"]
    assert len(image_parts) == 1
    url = image_parts[0]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == b"jpeg-bytes"

    captured.clear()
    await client.decide_next(make_mcq_step_request())
    content = captured["payload"]["messages"][1]["content"]
    parts = content if isinstance(content, list) else []
    assert not any(part.get("type") == "image_url" for part in parts), (
        "no image data may be sent when no frame evidence exists"
    )


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(
            '```json\n{"kind":"final","output":{"answer":"A"}}\n```',
            id="markdown-fences",
        ),
        pytest.param(
            '{"kind":"tool_calls","calls":[{"name":"open_url","arguments":{}}]}',
            id="unknown-tool",
        ),
        pytest.param(
            '{"kind":"final","output":{"answer":"A"},"model":"other"}',
            id="broader-fields",
        ),
        pytest.param('{"kind":"final","output":{"answer":"Z"}}', id="undeclared-final-label"),
    ],
)
@pytest.mark.asyncio
async def test_formal_decide_next_rejects_invalid_decisions_with_format_error(
    content: str,
) -> None:
    """Markdown, undeclared tools, extra fields, or bad labels must fail this test."""

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with pytest.raises(AgentDecisionFormatError):
        await make_formal_client(handler).decide_next(make_mcq_step_request())


@pytest.mark.asyncio
async def test_formal_decide_next_transport_failure_stays_measured_provider_error() -> None:
    """A transport failure must keep its attempted bytes and never earn a format repair."""

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": "service unavailable"})

    with pytest.raises(MeasuredProviderError) as excinfo:
        await make_formal_client(handler).decide_next(make_mcq_step_request())
    assert not isinstance(excinfo.value, AgentDecisionFormatError)
    assert excinfo.value.input_bytes > 0


@pytest.mark.asyncio
async def test_agentic_variant_steers_with_decide_next_and_never_legacy_planner(
    tmp_path,
) -> None:
    """An agentic run that still consults plan_tools must fail this test."""
    media = FakeFormalMedia()
    model = FakeFormalModel(ToolPlan(tools=("transcribe_audio",)))

    outcome = await FormalBenchmarkEngine(media=media, model=model).run_case(
        make_case(tmp_path),
        variant="agentic",
        work_dir=tmp_path / "agentic-decide",
        direct_input_mode="frames_2fps",
    )

    assert model.plan_calls == 0, "the new agentic runtime must not consult plan_tools"
    assert model.decision_calls >= 1, "the agentic runtime must steer through decide_next"
    assert outcome.answer == "A"
    assert outcome.correct is True
    assert outcome.verifier_passed is True
