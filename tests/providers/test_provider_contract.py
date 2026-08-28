"""Contract tests for the future public provider surface (RED until implemented)."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import httpx
import pytest
from vidsnap.providers.testing import assert_provider_contract

from vidsnap.config import QWEN_MODEL, TOKEN_PLAN_BASE_URL
from vidsnap.contracts import VideoGoal
from vidsnap.providers import (
    MockProvider,
    ProviderIdentity,
    ProviderPlugin,
    ProviderProtocol,
    QwenProfile,
    QwenProvider,
)


async def _mock_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    system = payload["messages"][0]["content"]
    if system.startswith("Choose evidence"):
        content = json.dumps({"tools": ["transcribe_audio"]})
    elif system.startswith("Steer"):
        content = json.dumps({"kind": "final", "output": {"summary": "mock"}})
    else:
        content = json.dumps({"summary": "mock", "claims": [], "required_sections": {}})
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5},
        },
    )


def make_qwen_provider() -> QwenProvider:
    return QwenProvider(
        api_key="fake-key",
        transport=httpx.MockTransport(_mock_handler),
    )


@pytest.mark.asyncio
async def test_both_providers_pass_the_same_contract_helper() -> None:
    await assert_provider_contract(make_qwen_provider())
    await assert_provider_contract(MockProvider())


@pytest.mark.asyncio
async def test_providers_satisfy_protocol_and_plugin_conformance() -> None:
    qwen = make_qwen_provider()
    mock = MockProvider()
    assert isinstance(qwen, ProviderProtocol)
    assert isinstance(mock, ProviderProtocol)
    assert isinstance(qwen, ProviderPlugin)
    assert isinstance(mock, ProviderPlugin)
    await assert_provider_contract(qwen)
    await assert_provider_contract(mock)


def test_qwen_identity_is_locked_and_immutable() -> None:
    profile = QwenProfile()
    assert profile.model == QWEN_MODEL == "qwen3.8-max"
    assert profile.base_url == TOKEN_PLAN_BASE_URL
    with pytest.raises(TypeError):
        QwenProfile(model="other-model")  # type: ignore[call-arg]

    identity = make_qwen_provider().identity
    assert isinstance(identity, ProviderIdentity)
    assert identity.id
    assert identity.model == QWEN_MODEL
    assert identity.base_url == TOKEN_PLAN_BASE_URL
    with pytest.raises(FrozenInstanceError):
        identity.model = "other-model"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_mock_provider_identity_and_analyze_are_deterministic() -> None:
    first = MockProvider()
    second = MockProvider()
    assert first.identity == second.identity

    goal = VideoGoal(objective="Summarize the demonstration")
    first_response = await first.analyze_evidence((), goal)
    second_response = await second.analyze_evidence((), goal)
    assert first_response == second_response
    assert first_response.result.summary == "mock"
    assert first_response.usage_reported is True
    assert first_response.input_tokens == 3
    assert first_response.output_tokens == 5
