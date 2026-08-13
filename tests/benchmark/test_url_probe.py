"""One-shot Direct URL compatibility probe safety contracts."""

from __future__ import annotations

import hashlib
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
    DirectUrlProbeResult,
    validate_probe_case,
)
from vidsnap.config import TOKEN_PLAN_BASE_URL

_FAKE_CREDENTIAL = "child-only-credential"


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
    subtitle_bytes = b"registered subtitle"
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe.REGISTERED_PROBE_SUBTITLE_SHA256",
        hashlib.sha256(subtitle_bytes).hexdigest(),
    )
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe.REGISTERED_PROBE_SUBTITLE_BYTES",
        len(subtitle_bytes),
    )
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe._sha256",
        lambda path: (
            REGISTERED_PROBE_SHA256
            if path.suffix == ".mp4"
            else hashlib.sha256(path.read_bytes()).hexdigest()
        ),
    )
    monkeypatch.setattr(
        "vidsnap.benchmark.url_probe._sha256_handle",
        lambda handle: REGISTERED_PROBE_SHA256,
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


def test_probe_preflight_rejects_changed_subtitle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A changed subtitle must not silently replace the registered Direct evidence."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)
    assert case.subtitle_path is not None
    case.subtitle_path.write_text("changed subtitle", encoding="utf-8")

    with pytest.raises(DirectUrlProbeFailure, match="local_validation"):
        validate_probe_case(case)


def test_probe_result_rejects_impossible_success_state() -> None:
    """A successful report cannot exceed one call or carry a failure category."""
    with pytest.raises(ValueError):
        DirectUrlProbeResult(
            status="PROBE_SUCCEEDED",
            case_id=REGISTERED_PROBE_CASE_ID,
            source_sha256=REGISTERED_PROBE_SHA256,
            source_bytes=REGISTERED_PROBE_SOURCE_BYTES,
            upload_status="succeeded",
            request_status="succeeded",
            model_calls=2,
            serialized_request_bytes=1,
            input_tokens=1,
            output_tokens=0,
            latency_seconds=1,
            failure_category="model_request",
        )


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
        BenchmarkProviderConfig(api_key=_FAKE_CREDENTIAL, base_url=TOKEN_PLAN_BASE_URL),
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
        _FAKE_CREDENTIAL,
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
async def test_probe_uploads_the_same_file_descriptor_that_was_validated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replacing the source path after policy lookup must not replace uploaded evidence."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)
    original_marker = b"ORIGINAL-END"
    replacement_marker = b"REPLACED-END"
    with case.source.open("r+b") as handle:
        handle.seek(-len(original_marker), 2)
        handle.write(original_marker)
    upload_body = b""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal upload_body
        if request.method == "GET":
            replacement = tmp_path / "replacement.mp4"
            with replacement.open("wb") as handle:
                handle.truncate(REGISTERED_PROBE_SOURCE_BYTES)
            with replacement.open("r+b") as handle:
                handle.seek(-len(replacement_marker), 2)
                handle.write(replacement_marker)
            replacement.replace(case.source)
            return httpx.Response(200, json=_policy_payload())
        if request.url.host == "dashscope-file-test.oss-cn-beijing.aliyuncs.com":
            upload_body = await request.aread()
            return httpx.Response(200)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "A"}}],
                "usage": {"prompt_tokens": 1234, "completion_tokens": 1},
            },
        )

    result = await DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key=_FAKE_CREDENTIAL, base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    ).run(case)

    assert result.status == "PROBE_SUCCEEDED"
    assert original_marker in upload_body
    assert replacement_marker not in upload_body


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
        BenchmarkProviderConfig(api_key=_FAKE_CREDENTIAL, base_url=TOKEN_PLAN_BASE_URL),
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
    assert _FAKE_CREDENTIAL not in serialized


@pytest.mark.asyncio
async def test_probe_rejects_non_private_upload_policy_before_transfer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public or overwriteable policy must stop before file bytes leave the process."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)
    calls = 0
    payload = _policy_payload()
    payload["data"]["x_oss_object_acl"] = "public-read"

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        return httpx.Response(200, json=payload)

    result = await DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key=_FAKE_CREDENTIAL, base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    ).run(case)

    assert calls == 1
    assert result.status == "PROBE_FAILED"
    assert result.failure_category == "upload_policy_compatibility"
    assert result.upload_status == "not_attempted"
    assert result.model_calls == 0


@pytest.mark.asyncio
async def test_probe_accepts_successful_usage_without_retaining_answer_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport success depends on provider usage, not answer text or choices."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_policy_payload())
        if request.url.host == "dashscope-file-test.oss-cn-beijing.aliyuncs.com":
            return httpx.Response(200)
        return httpx.Response(
            200,
            json={"usage": {"prompt_tokens": 1234, "completion_tokens": 0}},
        )

    result = await DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key=_FAKE_CREDENTIAL, base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    ).run(case)

    assert result.status == "PROBE_SUCCEEDED"
    assert result.input_tokens == 1234
    assert result.output_tokens == 0


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
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "invalid_parameter_error",
                    "message": "oss://private-object cannot resolve",
                }
            },
        )

    result = await DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key=_FAKE_CREDENTIAL, base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    ).run(case)

    assert calls == 3
    assert result.status == "PROBE_FAILED"
    assert result.failure_category == "provider_url_resolution"
    assert result.upload_status == "succeeded"
    assert result.request_status == "failed"
    assert result.model_calls == 1
    assert "oss://" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_probe_does_not_mislabel_unknown_client_error_as_url_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown 400 must remain a generic model-request failure."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_policy_payload())
        if request.url.host == "dashscope-file-test.oss-cn-beijing.aliyuncs.com":
            return httpx.Response(200)
        return httpx.Response(
            400,
            json={"error": {"code": "unrelated_request_error", "message": "private details"}},
        )

    result = await DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key=_FAKE_CREDENTIAL, base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    ).run(case)

    assert result.status == "PROBE_FAILED"
    assert result.failure_category == "model_request"
    assert "private details" not in result.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_stage", "expected_category"),
    (
        ("policy_schema", "upload_policy_compatibility"),
        ("upload", "upload_transfer"),
        ("model_http", "model_request"),
        ("response_schema", "response_schema"),
        ("usage", "usage_missing"),
    ),
)
async def test_probe_reports_each_network_failure_as_one_bounded_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    expected_category: str,
) -> None:
    """Every failed boundary must stop without raw provider details or a retry."""
    case = _registered_case(tmp_path)
    _patch_registered_hash(monkeypatch)
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.method == "GET":
            if failure_stage == "policy_schema":
                return httpx.Response(200, json={"data": {"private": "provider-body"}})
            return httpx.Response(200, json=_policy_payload())
        if request.url.host == "dashscope-file-test.oss-cn-beijing.aliyuncs.com":
            return httpx.Response(500 if failure_stage == "upload" else 200)
        if failure_stage == "model_http":
            return httpx.Response(500, json={"error": "provider-body"})
        if failure_stage == "response_schema":
            return httpx.Response(200, content=b"provider-body")
        if failure_stage == "usage":
            return httpx.Response(200, json={"private": "provider-body"})
        raise AssertionError("unexpected model request")

    result = await DirectUrlProbeClient(
        BenchmarkProviderConfig(api_key=_FAKE_CREDENTIAL, base_url=TOKEN_PLAN_BASE_URL),
        transport=httpx.MockTransport(handler),
    ).run(case)

    assert result.status == "PROBE_FAILED"
    assert result.failure_category == expected_category
    assert result.model_calls <= 1
    assert calls <= 3
    assert "provider-body" not in result.model_dump_json()
