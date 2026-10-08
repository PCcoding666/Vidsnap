"""Run-index summaries of bundles written by the current kernel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from test_failure_records import _FailingVideoModel
from test_fixed_policy import build_context, make_kernel

from vidsnap.contracts import ProviderFailure, VideoGoal
from vidsnap.providers import ProviderIdentity
from vidsnap.providers.base import ProviderError
from vidsnap.runtime import RecipeIdentity
from vidsnap.trace.pricing import load_price_table
from vidsnap.trace.run_index import summarize_run

_VIDEO_BYTES = b"deterministic-local-video-bytes"


def _price_table(tmp_path: Path, model: str) -> object:
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "vidsnap.price-table/v1",
                "currency": "CNY",
                "models": {
                    model: {"input_per_million_tokens": 1000.0, "output_per_million_tokens": 2000.0}
                },
            }
        ),
        encoding="utf-8",
    )
    return load_price_table(path)


@pytest.mark.asyncio
async def test_successful_run_summary_carries_header_usage_and_cost(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.provider_identity = ProviderIdentity(
        id="qwen", model="qwen3.8-max", base_url="https://h/v1"
    )
    context.recipe = RecipeIdentity(id="interview", version="0.1.1")
    context.task_adapter.goal = VideoGoal(objective="Summarize for editors")
    await make_kernel().run(context)
    prices = _price_table(tmp_path, "qwen3.8-max")

    record = summarize_run(context.bundle.path, command="analyze", price_table=prices)

    manifest = json.loads((context.bundle.path / "manifest.json").read_text())
    assert record["run_id"] == manifest["run_id"]
    assert record["started_at"] == manifest["created_at"]
    assert record["terminal_state"] == "SUCCEEDED"
    assert record["goal"] == "Summarize for editors"
    assert record["input_sha256"] == hashlib.sha256(_VIDEO_BYTES).hexdigest()
    assert record["input_size_bytes"] == len(_VIDEO_BYTES)
    assert record["input_duration_seconds"] == 8.0
    assert (record["provider"], record["model"]) == ("qwen", "qwen3.8-max")
    assert record["recipe"] == "interview"
    assert record["policy"] == "FixedPolicy"
    assert record["model_calls"] == 1
    assert record["tool_calls"] == 2
    assert record["failed_gates"] == []
    assert record["failure_category"] is None
    assert record["failure_reason"] is None
    assert isinstance(record["duration_ms"], int) and record["duration_ms"] >= 0
    # FakeVideoModel reports 11 input and 7 output tokens for its one request.
    assert (record["input_tokens"], record["output_tokens"]) == (11, 7)
    assert record["tokens_reported"] is True
    cost = record["cost"]
    assert isinstance(cost, dict)
    assert cost["amount"] == pytest.approx((11 * 1000.0 + 7 * 2000.0) / 1_000_000)
    # Speech recognition ran in this run and is not priced, so the cost is incomplete.
    assert cost["complete"] is False
    assert cost["note"] == "speech_recognition_not_priced"
    assert cost["currency"] == "CNY"


@pytest.mark.asyncio
async def test_silent_run_cost_covers_every_priced_call(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=False)
    context.provider_identity = ProviderIdentity(
        id="qwen", model="qwen3.8-max", base_url="https://h/v1"
    )
    await make_kernel().run(context)

    record = summarize_run(
        context.bundle.path,
        command="analyze",
        price_table=_price_table(tmp_path, "qwen3.8-max"),
    )

    cost = record["cost"]
    assert isinstance(cost, dict)
    assert cost["complete"] is True
    assert cost["note"] is None


@pytest.mark.asyncio
async def test_run_without_model_requests_has_no_priced_amount(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.provider_identity = ProviderIdentity(
        id="qwen", model="qwen3.8-max", base_url="https://h/v1"
    )
    context.policy = context.policy.model_copy(update={"max_tool_calls": 0})
    await make_kernel().run(context)

    record = summarize_run(
        context.bundle.path,
        command="analyze",
        price_table=_price_table(tmp_path, "qwen3.8-max"),
    )

    assert record["terminal_state"] == "EXHAUSTED"
    cost = record["cost"]
    assert isinstance(cost, dict)
    assert cost["amount"] is None
    assert cost["note"] == "no_model_requests"


@pytest.mark.asyncio
async def test_failed_run_summary_carries_the_structured_failure(tmp_path: Path) -> None:
    context, *_ = build_context(tmp_path, has_audio=True)
    context.provider_identity = ProviderIdentity(
        id="qwen", model="qwen3.8-max", base_url="https://h/v1"
    )
    failure = ProviderFailure(category="read_timeout", input_bytes=2048)
    context.task_model = _FailingVideoModel(ProviderError("timed out", failure=failure))
    await make_kernel().run(context)

    record = summarize_run(
        context.bundle.path,
        command="analyze",
        price_table=_price_table(tmp_path, "qwen3.8-max"),
    )

    assert record["terminal_state"] == "FAILED"
    assert record["failure_category"] == "read_timeout"
    assert record["http_status"] is None
    assert record["failure_reason"] == "provider error"
    assert record["failed_gates"] is None
    assert record["tokens_reported"] is False
    cost = record["cost"]
    assert isinstance(cost, dict)
    assert cost["amount"] is None
    assert cost["note"] == "usage_not_reported"
