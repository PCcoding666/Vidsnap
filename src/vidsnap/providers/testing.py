"""Deterministic conformance probe every bounded provider must satisfy."""

from __future__ import annotations

from pydantic import JsonValue

from vidsnap.contracts import VideoAnalysisResult, VideoGoal
from vidsnap.providers.base import (
    AgentDecisionResponse,
    AgentStepRequest,
    ModelResponse,
    ProviderIdentity,
    ProviderProtocol,
    ToolPlanResponse,
)
from vidsnap.video.probe import MediaProbe

_TOOL_SCHEMAS: tuple[dict[str, JsonValue], ...] = (
    {
        "name": "transcribe_audio",
        "type": "object",
        "properties": {},
        "required": [],
    },
    {
        "name": "sample_evidence",
        "type": "object",
        "properties": {},
        "required": [],
    },
)


async def assert_provider_contract(provider: ProviderProtocol) -> None:
    """Assert the runtime provider contract against fixed, deterministic fixtures."""
    assert isinstance(provider, ProviderProtocol)

    identity = provider.identity
    assert isinstance(identity, ProviderIdentity)
    assert identity.id
    assert identity.model
    assert identity.base_url

    goal = VideoGoal(objective="Summarize the video faithfully with timestamped claims.")
    probe = MediaProbe(duration_seconds=1.0, fps=1.0, width=1, height=1, has_audio=True)
    request = AgentStepRequest(
        goal=goal,
        probe=probe,
        evidence=(),
        tool_results=(),
        tool_schemas=_TOOL_SCHEMAS,
        output_schema=VideoAnalysisResult.model_json_schema(),
        remaining_model_calls=1,
        remaining_tool_calls=1,
        remaining_frames=1,
    )

    model_response = await provider.analyze_evidence((), goal)
    plan_response = await provider.plan_tools(probe, goal)
    decision_response = await provider.decide_next(request)

    assert isinstance(model_response, ModelResponse)
    assert model_response.input_tokens >= 0
    assert model_response.output_tokens >= 0

    assert isinstance(plan_response, ToolPlanResponse)
    assert plan_response.input_tokens >= 0
    assert plan_response.output_tokens >= 0
    assert plan_response.input_bytes >= 0

    assert isinstance(decision_response, AgentDecisionResponse)
    assert decision_response.usage.model_calls >= 0
    assert decision_response.usage.input_bytes >= 0
    assert decision_response.usage.input_tokens >= 0
    assert decision_response.usage.output_tokens >= 0
