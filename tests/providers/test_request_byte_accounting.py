"""Offline tests proving all three Qwen paths report real request-body bytes."""

from __future__ import annotations

import json

import httpx
import pytest

from vidsnap.contracts import Evidence, VideoGoal
from vidsnap.providers.base import AgentStepRequest
from vidsnap.providers.qwen import QwenCompatibleClient
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.probe import MediaProbe


def _ok_response(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "choices": [{"message": {"content": '{"summary":"ok","claims":[]}'}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }
    body.update(overrides)
    return body


def _decision_response() -> dict[str, object]:
    decision = {
        "kind": "tool_calls",
        "calls": [{"name": "sample_evidence", "arguments": {"max_frames": 1}}],
    }
    return {
        "choices": [{"message": {"content": json.dumps(decision)}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }


@pytest.mark.asyncio
async def test_analyze_evidence_reports_real_request_body_bytes() -> None:
    """analyze_evidence must measure actual HTTP request content, not guess."""
    captured_bytes: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_bytes.append(len(request.content))
        return httpx.Response(200, json=_ok_response())

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    goal = VideoGoal(objective="总结这段中文播客内容并提取关键论点")
    evidence = [
        Evidence(
            id="seg-1",
            start_seconds=0.0,
            end_seconds=30.0,
            modality="transcript",
            content='演讲者讨论了"人工智能"在医疗领域的应用\n包括诊断和药物研发',
        ),
    ]
    response = await client.analyze_evidence(evidence, goal)

    assert len(captured_bytes) == 1
    expected = captured_bytes[0]
    assert expected > 0
    assert response.input_bytes == expected


@pytest.mark.asyncio
async def test_plan_tools_uses_real_request_content_length() -> None:
    """plan_tools input_bytes must equal the actual HTTP request body length."""
    captured_bytes: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_bytes.append(len(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"tools":["transcribe_audio"]}'}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    goal = VideoGoal(objective='分析视频中的"引用"和转义字符\t\n处理')
    response = await client.plan_tools(
        MediaProbe(duration_seconds=60, fps=30, width=1920, height=1080, has_audio=True),
        goal,
    )

    assert len(captured_bytes) == 1
    assert response.input_bytes == captured_bytes[0]


@pytest.mark.asyncio
async def test_decide_next_uses_real_request_content_length() -> None:
    """decide_next input_bytes must equal the actual HTTP request body length."""
    captured_bytes: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_bytes.append(len(request.content))
        return httpx.Response(200, json=_decision_response())

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    request = AgentStepRequest(
        goal=VideoGoal(objective='检查中文内容和特殊字符: "引号", \\反斜杠, \t制表符'),
        probe=MediaProbe(duration_seconds=30, fps=24, width=640, height=360, has_audio=False),
        evidence=(
            Evidence(
                id="e1",
                start_seconds=0.0,
                end_seconds=10.0,
                modality="transcript",
                content='包含"嵌套引号"和\\路径分隔符的文本',
            ),
        ),
        tool_results=(),
        tool_schemas=(
            {"name": "transcribe_audio", "input_schema": {"type": "object"}},
            {"name": "sample_evidence", "input_schema": {"type": "object"}},
        ),
        output_schema={"type": "object"},
        remaining_model_calls=10,
        remaining_tool_calls=5,
        remaining_frames=50,
    )
    response = await client.decide_next(request)

    assert len(captured_bytes) == 1
    assert response.usage.input_bytes == captured_bytes[0]


@pytest.mark.asyncio
async def test_video_analysis_adapter_propagates_input_bytes() -> None:
    """VideoAnalysisTaskAdapter must carry input_bytes from ModelResponse into ProviderUsage."""
    captured_bytes: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_bytes.append(len(request.content))
        return httpx.Response(200, json=_ok_response())

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    adapter = VideoAnalysisTaskAdapter(goal=VideoGoal(objective="测试适配器字节计量"))
    result, usage = await adapter.request_final(
        model=client,
        evidence=[],
        probe=MediaProbe(duration_seconds=10, fps=24, width=640, height=360, has_audio=False),
    )

    del result
    assert len(captured_bytes) == 1
    assert usage.input_bytes == captured_bytes[0]
    assert usage.model_calls == 1


def test_model_response_positional_args_preserve_usage_reported_semantics() -> None:
    """Legacy callers using ModelResponse(result, tokens_in, tokens_out, True) must still work."""
    from vidsnap.contracts import VideoAnalysisResult
    from vidsnap.providers.base import ModelResponse

    result = VideoAnalysisResult(summary="s", claims=[])
    response = ModelResponse(result, 3, 5, True)
    assert response.input_tokens == 3
    assert response.output_tokens == 5
    assert response.usage_reported is True
    assert response.input_bytes == 0


@pytest.mark.asyncio
async def test_analyze_evidence_unreported_usage_still_records_input_bytes() -> None:
    """When provider omits usage, input_bytes must still be accurate and reported=False."""
    captured_bytes: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_bytes.append(len(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary":"ok","claims":[]}'}}]},
        )

    client = QwenCompatibleClient(api_key="test", transport=httpx.MockTransport(handler))
    response = await client.analyze_evidence([], VideoGoal(objective="测试无usage时字节计量"))

    assert len(captured_bytes) == 1
    assert response.input_bytes == captured_bytes[0]
    assert response.usage_reported is False
    assert response.input_tokens == 0
    assert response.output_tokens == 0
