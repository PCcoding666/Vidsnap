"""The default stack sends ASR to the public endpoint and text to Token Plan.

Both default clients are built by ``VideoHarness`` from one ``HarnessConfig``.
``httpx.AsyncClient`` is wrapped so every client gets an offline mock transport
that records the request; nothing here touches the network.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from vidsnap.config import DASHSCOPE_ASR_BASE_URL, HarnessConfig
from vidsnap.contracts import VideoGoal
from vidsnap.eval.providers import DASHSCOPE_BASE_URL
from vidsnap.harness import VideoHarness

_TEXT_CREDENTIAL = "text-credential-for-tests"
_ASR_CREDENTIAL = "asr-credential-for-tests"
_TOKEN_PLAN_URL = (
    "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
)
_ASR_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def _record_requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if json.loads(request.content)["model"] == "qwen3-asr-flash":
            return httpx.Response(200, json={"choices": [{"message": {"content": "heard"}}]})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary":"ok","claims":[]}'}}]},
        )

    real_client = httpx.AsyncClient

    def client_with_mock_transport(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_with_mock_transport)
    return captured


@pytest.mark.asyncio
async def test_default_harness_splits_text_and_speech_between_the_two_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _record_requests(monkeypatch)
    harness = VideoHarness(
        HarnessConfig(
            api_key=_TEXT_CREDENTIAL,
            asr_api_key=_ASR_CREDENTIAL,
            request_timeout_seconds=77.0,
        )
    )
    assert harness.recognizer is not None

    await harness.model.analyze_evidence([], VideoGoal(objective="Summarize"))
    await harness.recognizer.transcribe(b"audio")

    text_request, asr_request = captured
    assert str(text_request.url) == _TOKEN_PLAN_URL
    assert text_request.headers["Authorization"] == f"Bearer {_TEXT_CREDENTIAL}"
    assert json.loads(text_request.content)["model"] == "qwen3.8-max"
    assert str(asr_request.url) == _ASR_URL
    assert asr_request.headers["Authorization"] == f"Bearer {_ASR_CREDENTIAL}"
    assert json.loads(asr_request.content)["model"] == "qwen3-asr-flash"
    for request in (text_request, asr_request):
        assert request.extensions["timeout"] == {
            "connect": 77.0,
            "read": 77.0,
            "write": 77.0,
            "pool": 77.0,
        }


@pytest.mark.asyncio
async def test_default_harness_reuses_the_text_key_for_speech_when_no_asr_key_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _record_requests(monkeypatch)
    harness = VideoHarness(HarnessConfig(api_key=_TEXT_CREDENTIAL))
    assert harness.recognizer is not None

    await harness.recognizer.transcribe(b"audio")

    (asr_request,) = captured
    assert str(asr_request.url) == _ASR_URL
    assert asr_request.headers["Authorization"] == f"Bearer {_TEXT_CREDENTIAL}"
    assert asr_request.extensions["timeout"]["write"] == 120.0


def test_default_harness_reads_the_asr_key_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIDSNAP_ASR_API_KEY", _ASR_CREDENTIAL)
    monkeypatch.setenv("VIDSNAP_QWEN_API_KEY", _TEXT_CREDENTIAL)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)

    config = HarnessConfig.from_env()

    assert config.api_key == _TEXT_CREDENTIAL
    assert config.resolved_asr_api_key == _ASR_CREDENTIAL


def test_eval_package_uses_the_same_public_endpoint_constant_as_the_harness() -> None:
    assert DASHSCOPE_BASE_URL == DASHSCOPE_ASR_BASE_URL
