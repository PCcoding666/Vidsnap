"""One-shot Direct URL compatibility probe safety contracts."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import BenchmarkProviderConfig
from vidsnap.benchmark.url_probe import (
    DIRECT_URL_PROBE_FPS,
    REGISTERED_PROBE_CASE_ID,
    REGISTERED_PROBE_SHA256,
    REGISTERED_PROBE_SOURCE_BYTES,
    DirectUrlProbeClient,
    DirectUrlProbeFailure,
    validate_probe_case,
)
from vidsnap.config import TOKEN_PLAN_BASE_URL


def _registered_case(tmp_path: Path) -> FormalCase:
    source = tmp_path / "registered.mp4"
    with source.open("wb") as handle:
        handle.truncate(REGISTERED_PROBE_SOURCE_BYTES)
    subtitle = tmp_path / "registered.srt"
    subtitle.write_text("registered subtitle", encoding="utf-8")
    return FormalCase(
        case_id=REGISTERED_PROBE_CASE_ID,
        dataset="Video-MME",
        dataset_version="revision",
        dataset_license="Internal non-commercial research only.",
        source_url="https://github.com/MME-Benchmarks/Video-MME",
        source=source,
        source_sha256=REGISTERED_PROBE_SHA256,
        task_family="Action Recognition",
        question="What happens?",
        options={"A": "First", "B": "Second"},
        answer="A",
        subtitle_path=subtitle,
        has_audio=True,
        duration_stratum="long",
        requirements=("visual", "temporal"),
        expected_tools=("sample_evidence",),
        tool_annotation_reason="visual-required",
    )


def _patch_registered_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe._sha256",
        lambda path: REGISTERED_PROBE_SHA256,
    )


def _policy_payload() -> dict[str, object]:
    return {
        "request_id": "safe-request-id",
        "data": {
            "policy": "private-policy-value",
            "signature": "private-signature-value",
            "upload_dir": "dashscope-instant/private/object",
            "upload_host": "https://dashscope-file-test.oss-cn-beijing.aliyuncs.com",
            "expire_in_seconds": 300,
            "max_file_size_mb": 100,
            "capacity_limit_mb": 1000,
            "oss_access_key_id": "private-access-id",
            "x_oss_object_acl": "private",
            "x_oss_forbid_overwrite": "true",
        },
    }


def test_probe_preflight_accepts_only_registered_local_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing the bound case, digest, or source bytes must stop before network access."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)

    validate_probe_case(case)

    for changed in (
        case.model_copy(update={"case_id": "videomme:other"}),
        case.model_copy(update={"source_sha256": "0" * 64}),
    ):
        with pytest.raises(DirectUrlProbeFailure, match="local_validation"):
            validate_probe_case(changed)
    case.source.write_bytes(b"wrong-size")
    with pytest.raises(DirectUrlProbeFailure, match="local_validation"):
        validate_probe_case(case)


@pytest.mark.asyncio
async def test_probe_uploads_once_and_calls_fixed_qwen_video_url_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry, changed model/fps, public upload, or persisted provider content must fail."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)
    requests: list[tuple[str, str]] = []
    upload_body = b""
    model_payload: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal upload_body, model_payload
        requests.append((request.method, str(request.url)))
        if request.method == "GET":
            assert dict(request.url.params) == {
                "action": "getPolicy",
                "model": "qwen3.8-max",
            }
            return httpx.Response(200, json=_policy_payload())
        if request.url.host == "dashscope-file-test.oss-cn-beijing.aliyuncs.com":
            upload_body = await request.aread()
            return httpx.Response(200)
        model_payload = json.loads(await request.aread())
        assert request.headers["X-DashScope-OssResourceResolve"] == "enable"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "A"}}],
                "usage": {"prompt_tokens": 1234, "completion_tokens": 1},
            },
        )

    client = DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key="child-only-credential", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    )

    result = await client.run(case)

    assert [method for method, _ in requests] == ["GET", "POST", "POST"]
    assert requests[0][1].startswith("https://dashscope.aliyuncs.com/api/v1/uploads?")
    assert requests[2][1] == f"{TOKEN_PLAN_BASE_URL}/chat/completions"
    assert b'name="x-oss-object-acl"' in upload_body
    assert b"private" in upload_body
    assert upload_body.count(b'name="file"') == 1
    content = model_payload["messages"][1]["content"]
    assert model_payload["model"] == "qwen3.8-max"
    assert content[1]["type"] == "video_url"
    assert content[1]["fps"] == DIRECT_URL_PROBE_FPS == 2
    assert content[1]["video_url"]["url"].startswith("oss://")
    assert json.loads(content[0]["text"])["subtitle"] == "registered subtitle"
    assert result.status == "PROBE_SUCCEEDED"
    assert result.model_calls == 1
    assert result.input_tokens == 1234
    assert result.output_tokens == 1
    assert result.source_bytes == 15_543_000
    assert result.upload_status == "succeeded"
    assert result.request_status == "succeeded"
    assert result.failure_category is None
    assert result.serialized_request_bytes > 0
    serialized = repr(result) + result.model_dump_json()
    for forbidden in (
        "child-only-credential",
        "private-policy-value",
        "private-signature-value",
        "private-access-id",
        "dashscope-file-test",
        "dashscope-instant",
        "oss://",
        '"A"',
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_probe_sanitizes_upload_policy_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider errors must become bounded categories without preserving their bodies."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(
            403,
            json={"error": "private-policy-value oss://private-object child-only-credential"},
        )

    result = await DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key="child-only-credential", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    ).run(case)

    assert calls == 1
    assert result.status == "PROBE_FAILED"
    assert result.failure_category == "upload_policy_compatibility"
    assert result.upload_status == "not_attempted"
    assert result.request_status == "not_attempted"
    assert result.model_calls == 0
    serialized = repr(result) + result.model_dump_json()
    assert "private-policy-value" not in serialized
    assert "oss://" not in serialized
    assert "child-only-credential" not in serialized


@pytest.mark.asyncio
async def test_probe_stops_after_one_rejected_model_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A URL-resolution rejection must not trigger retry or another transport."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.method == "GET":
            return httpx.Response(200, json=_policy_payload())
        if request.url.host == "dashscope-file-test.oss-cn-beijing.aliyuncs.com":
            return httpx.Response(200)
        return httpx.Response(400, json={"error": "oss://private-object cannot resolve"})

    result = await DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key="child-only-credential", base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    ).run(case)

    assert calls == 3
    assert result.status == "PROBE_FAILED"
    assert result.failure_category == "provider_url_resolution"
    assert result.upload_status == "succeeded"
    assert result.request_status == "failed"
    assert result.model_calls == 1
    assert "oss://" not in result.model_dump_json()
