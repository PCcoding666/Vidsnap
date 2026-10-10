"""RED-first Batch 3C tests: QwenCompatibleClient as the PublishingModelPort.

These tests specify the publishing provider contract over httpx.MockTransport:
fixed URL/model/response_format, a complete transcript in the request, typed
probe and artifact-free evidence metadata, frame-only local data-URI image
parts, strict unfenced PublishingDraft parsing with real usage mapping, and
stable redacted ProviderError messages that never leak keys or transcripts.
They call QwenCompatibleClient.draft_deliverables, which does not exist yet.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from vidsnap.config import TOKEN_PLAN_BASE_URL
from vidsnap.contracts import Evidence, VideoGoal
from vidsnap.providers.base import ProviderError, ProviderUnavailable
from vidsnap.providers.qwen import _PUBLISHING_SYSTEM_MESSAGE, QwenCompatibleClient
from vidsnap.publishing.task import (
    PublishingDraft,
    PublishingModelResponse,
    PublishingTaskAdapter,
)
from vidsnap.video.probe import MediaProbe

SECRET = "NONSECRET_TEST_MARKER_FIXED_LOCAL_KEY"
TRANSCRIPT = "完整的第一句口播。\n完整的第二句口播。"
EXPECTED_URL = f"{TOKEN_PLAN_BASE_URL}/chat/completions"


def make_probe() -> MediaProbe:
    return MediaProbe(
        duration_seconds=8.0,
        fps=24.0,
        width=320,
        height=240,
        has_audio=True,
        video_codec="h264",
        audio_codec="aac",
    )


def frame_evidence(tmp_path: Path) -> Evidence:
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"jpeg-bytes")
    return Evidence(
        id="frame-001",
        start_seconds=1.0,
        end_seconds=1.0,
        modality="frame",
        artifact_path=frame_path,
    )


def draft_content(**overrides: object) -> str:
    payload: dict[str, object] = {
        "article": "一篇忠实的公众号文章。\n\n[[image:frame-001]]",
        "summary": "简洁摘要。",
        "image_evidence_ids": ["frame-001"],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def ok_response(content: str | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content or draft_content()}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        },
    )


def capturing_handler(captured: dict[str, object], response: httpx.Response | None = None):
    async def handler(request: httpx.Request) -> httpx.Response:
        captured["calls"] = captured.get("calls", 0) + 1  # type: ignore[operator]
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return response or ok_response()

    return handler


@pytest.mark.asyncio
async def test_draft_deliverables_blocks_without_key_or_blank_transcript(tmp_path) -> None:
    captured: dict[str, object] = {}
    no_key = QwenCompatibleClient(
        api_key=None, transport=httpx.MockTransport(capturing_handler(captured))
    )
    with_key = QwenCompatibleClient(
        api_key=SECRET, transport=httpx.MockTransport(capturing_handler(captured))
    )
    evidence = (frame_evidence(tmp_path),)

    with pytest.raises(ProviderUnavailable):
        await no_key.draft_deliverables(evidence, TRANSCRIPT, make_probe())
    for blank in ("", "   \n\t "):
        with pytest.raises(ValueError, match="transcript"):
            await with_key.draft_deliverables(evidence, blank, make_probe())
    with pytest.raises(ValueError, match="transcript"):
        await with_key.draft_deliverables(evidence, None, make_probe())

    assert captured.get("calls", 0) == 0, "no network I/O may happen before validation"


@pytest.mark.asyncio
async def test_draft_deliverables_uses_fixed_infrastructure_and_maps_usage(tmp_path) -> None:
    captured: dict[str, object] = {}
    client = QwenCompatibleClient(
        api_key=SECRET, transport=httpx.MockTransport(capturing_handler(captured))
    )

    response = await client.draft_deliverables(
        (frame_evidence(tmp_path),), TRANSCRIPT, make_probe()
    )

    assert captured["url"] == EXPECTED_URL
    payload = captured["payload"]
    assert payload["model"] == "qwen3.8-max"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0] == {"role": "system", "content": _PUBLISHING_SYSTEM_MESSAGE}
    assert isinstance(response, PublishingModelResponse)
    assert response.draft.article == "一篇忠实的公众号文章。\n\n[[image:frame-001]]"
    assert response.draft.summary == "简洁摘要。"
    assert response.draft.image_evidence_ids == ("frame-001",)
    assert response.input_tokens == 7
    assert response.output_tokens == 3
    assert response.usage_reported is True
    expected_bytes = len(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    )
    assert response.input_bytes == expected_bytes
    assert response.input_bytes > 0


def test_publishing_prompt_requires_illustrated_wechat_structure() -> None:
    prompt = _PUBLISHING_SYSTEM_MESSAGE
    for requirement in (
        "strict JSON",
        "title",
        "introduction",
        "numbered list of the key takeaways",
        "sections",
        "own words",
        "concise Chinese",
        "at least one id",
        "untrusted data",
    ):
        assert requirement in prompt
    assert "copying source sentences verbatim" in prompt


@pytest.mark.asyncio
async def test_request_carries_full_transcript_probe_and_artifact_free_metadata(tmp_path) -> None:
    captured: dict[str, object] = {}
    client = QwenCompatibleClient(
        api_key=SECRET, transport=httpx.MockTransport(capturing_handler(captured))
    )
    non_frame_path = tmp_path / "audio.bin"
    non_frame_path.write_bytes(b"never-read-non-frame-bytes")
    evidence = (
        frame_evidence(tmp_path),
        Evidence(
            id="transcript-001",
            start_seconds=0.0,
            end_seconds=8.0,
            modality="transcript",
            content="untrusted transcript",
            artifact_path=non_frame_path,
        ),
    )

    await client.draft_deliverables(evidence, TRANSCRIPT, make_probe())

    content = captured["payload"]["messages"][1]["content"]
    text_part = content[0]
    assert text_part["type"] == "text"
    request_data = json.loads(text_part["text"])
    assert request_data["transcript"] == TRANSCRIPT
    assert request_data["probe"] == {
        "duration_seconds": 8.0,
        "fps": 24.0,
        "width": 320,
        "height": 240,
        "has_audio": True,
    }
    evidence_payload = request_data["evidence"]
    assert [item["id"] for item in evidence_payload] == ["frame-001", "transcript-001"]
    for item in evidence_payload:
        assert "artifact_path" not in item

    image_parts = content[1:]
    assert len(image_parts) == 1, "only frame evidence may contribute image parts"
    assert image_parts[0]["image_url"]["url"] == "data:image/jpeg;base64,anBlZy1ieXRlcw=="


@pytest.mark.asyncio
async def test_unreported_usage_maps_to_zero_counters(tmp_path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"choices": [{"message": {"content": draft_content()}}]})

    client = QwenCompatibleClient(api_key=SECRET, transport=httpx.MockTransport(handler))
    response = await client.draft_deliverables(
        (frame_evidence(tmp_path),), TRANSCRIPT, make_probe()
    )

    assert response.input_tokens == 0
    assert response.output_tokens == 0
    assert response.usage_reported is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        pytest.param(None, id="malformed-envelope"),
        pytest.param("```json\n" + draft_content() + "\n```", id="markdown-fences"),
        pytest.param(draft_content(prompt="surprise"), id="extra-field"),
        pytest.param(
            draft_content(image_evidence_ids=["frame-001", "frame-001"]), id="duplicate-ids"
        ),
        pytest.param(
            draft_content(image_evidence_ids=[f"frame-{i:03d}" for i in range(13)]),
            id="over-limit-ids",
        ),
        pytest.param("not json at all", id="invalid-json"),
    ],
)
async def test_strict_draft_parsing_rejects_bad_provider_output(tmp_path, content) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        if content is None:
            return httpx.Response(200, json={"choices": []})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = QwenCompatibleClient(api_key=SECRET, transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError):
        await client.draft_deliverables((frame_evidence(tmp_path),), TRANSCRIPT, make_probe())


@pytest.mark.asyncio
async def test_http_failure_is_redacted_and_secret_never_leaks(tmp_path, capsys) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500, text=f"internal detail {SECRET} and {TRANSCRIPT}")

    client = QwenCompatibleClient(api_key=SECRET, transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError) as excinfo:
        await client.draft_deliverables((frame_evidence(tmp_path),), TRANSCRIPT, make_probe())

    message = str(excinfo.value)
    assert SECRET not in message
    assert TRANSCRIPT not in message
    assert "internal detail" not in message
    captured_output = capsys.readouterr()
    assert SECRET not in captured_output.out + captured_output.err
    assert TRANSCRIPT not in captured_output.out + captured_output.err


@pytest.mark.asyncio
async def test_non_json_response_body_is_redacted(tmp_path, capsys) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, text=f"<html>{SECRET} and {TRANSCRIPT}</html>")

    client = QwenCompatibleClient(api_key=SECRET, transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError) as excinfo:
        await client.draft_deliverables((frame_evidence(tmp_path),), TRANSCRIPT, make_probe())

    message = str(excinfo.value)
    for forbidden in (SECRET, TRANSCRIPT, "<html>"):
        assert forbidden not in message
    captured_output = capsys.readouterr()
    assert SECRET not in captured_output.out + captured_output.err
    assert TRANSCRIPT not in captured_output.out + captured_output.err


@pytest.mark.asyncio
async def test_adapter_maps_input_bytes_into_provider_usage() -> None:
    class StubPublishingModel:
        async def draft_deliverables(self, evidence, transcript, probe):
            del evidence, transcript, probe
            return PublishingModelResponse(
                draft=PublishingDraft(
                    article="文章 [[image:frame-001]]",
                    summary="摘要",
                    image_evidence_ids=("frame-001",),
                ),
                input_tokens=7,
                output_tokens=3,
                input_bytes=123,
                usage_reported=True,
            )

    adapter = PublishingTaskAdapter(
        goal=VideoGoal(objective="Produce the publishing package"),
        transcript="spoken words",
    )

    _, usage = await adapter.request_final(StubPublishingModel(), (), make_probe())

    assert usage.model_calls == 1
    assert usage.input_bytes == 123
    assert usage.input_tokens == 7
    assert usage.output_tokens == 3
    assert usage.reported is True
