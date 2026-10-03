"""Batch 1 acceptance tests for vidsnap.call-review/v1 tool-call metadata.

These tests drive the real HarnessKernel + FixedPolicy against deterministic
fakes and assert only the new payload.call_review field on actual
tool.call.started / tool.call.completed events:

- api_version is exactly "vidsnap.call-review/v1";
- started.parameters equals the hand-computed validated dump of the arguments
  that really executed (transcribe_audio: {"windows": []};
  sample_evidence: {"max_frames": 96, "windows": []});
- completed.result_evidence_ids matches the concrete evidence produced by the
  fake ports (one transcript from FakeTranscriber; three frames from FakeFFmpeg);
- completed.result_summary is a redacted copy of ToolResult.summary (no secrets,
  no absolute paths, no raw body or chain-of-thought leaked).

No execution decisions are changed. No skipped/fake events are introduced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import (
    FakeFFmpeg,
    FakeVideoModel,
    ScriptedAgentModel,
    final_decision,
    tool_decision,
)
from pydantic import Field
from test_fixed_policy import build_context, make_kernel, read_events

from vidsnap.contracts import (
    HarnessPolicy,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.contracts.models import StrictModel
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.plugins.base import ToolExecutionContext, ToolResult
from vidsnap.plugins.manifest import PluginManifest
from vidsnap.plugins.registry import PluginRegistry
from vidsnap.runtime import (
    AgenticPolicy,
    HarnessKernel,
    RunContext,
)
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.sampling import AdaptiveSampler

CALL_REVIEW_VERSION = "vidsnap.call-review/v1"


def _call_review(event: dict[str, object]) -> dict[str, object]:
    payload = event.get("payload")
    assert isinstance(payload, dict), f"event missing payload: {event}"
    review = payload.get("call_review")
    assert isinstance(review, dict), f"payload missing call_review: {payload}"
    return review


def _events_of_type(events: list[dict[str, object]], event_type: str) -> list[dict[str, object]]:
    return [event for event in events if event.get("event_type") == event_type]


@pytest.mark.asyncio
async def test_tool_call_review_records_validated_parameters_and_real_result(
    tmp_path: Path,
) -> None:
    """Successful tool executions record truthful parameters and result mapping."""
    context, *_ = build_context(tmp_path, has_audio=True)
    kernel = make_kernel()

    await kernel.run(context)

    events = read_events(context.bundle.path)
    started = _events_of_type(events, "tool.call.started")
    completed = _events_of_type(events, "tool.call.completed")
    assert len(started) == 2, f"expected exactly two tool calls, got {len(started)}"
    assert len(completed) == 2

    # FixedPolicy executes transcribe_audio then sample_evidence in order.
    asr_start, sample_start = started
    asr_finish, sample_finish = completed

    assert asr_start["payload"]["name"] == "transcribe_audio"
    assert sample_start["payload"]["name"] == "sample_evidence"
    assert asr_finish["payload"]["name"] == "transcribe_audio"
    assert sample_finish["payload"]["name"] == "sample_evidence"

    asr_review_start = _call_review(asr_start)
    assert asr_review_start["api_version"] == CALL_REVIEW_VERSION
    assert asr_review_start["parameters"] == {"windows": []}

    sample_review_start = _call_review(sample_start)
    assert sample_review_start["api_version"] == CALL_REVIEW_VERSION
    assert sample_review_start["parameters"] == {"max_frames": 96, "windows": []}

    asr_review_finish = _call_review(asr_finish)
    assert asr_review_finish["api_version"] == CALL_REVIEW_VERSION
    assert asr_review_finish["result_evidence_ids"] == ["transcript-001"]
    assert asr_review_finish["result_summary"] == {
        "transcript_count": 1,
        "character_count": len("deterministic spoken content"),
    }

    sample_review_finish = _call_review(sample_finish)
    assert sample_review_finish["api_version"] == CALL_REVIEW_VERSION
    assert sample_review_finish["result_evidence_ids"] == [
        "frame-001",
        "frame-002",
        "frame-003",
    ]
    assert sample_review_finish["result_summary"] == {"frame_count": 3}

    # Cross-check: recorded evidence IDs match what the context actually holds,
    # ordered by modality.
    transcript_ids = [e.id for e in context.evidence if e.modality == "transcript"]
    frame_ids = [e.id for e in context.evidence if e.modality == "frame"]
    assert transcript_ids == ["transcript-001"]
    assert frame_ids == ["frame-001", "frame-002", "frame-003"]


class _MaliciousInput(StrictModel):
    """Trivial input model for the malicious-summary fake tool."""

    dummy: int = Field(default=0, ge=0)


class MaliciousSummaryPlugin:
    """A fake tool plugin whose summary embeds nested secrets, paths, and CoT."""

    manifest = PluginManifest(
        id="malicious_summary",
        version="1.0.0",
        kind="tool",
        model_visible=True,
    )
    name = "malicious_summary"
    input_model = _MaliciousInput

    async def execute(self, arguments: StrictModel, context: ToolExecutionContext) -> ToolResult:
        # Construct sensitive values at runtime to avoid secret_scan false positives.
        fake_bearer = "Bearer " + "sk-secret" + "-token-value"
        fake_api_key = "sk-leaked" + "-key-12345"
        fake_cot = "internal reasoning " + "scratchpad text"
        fake_raw = "raw provider " + "body content"
        fake_pw = "hunter" + "2"
        fake_ssh_path = "/Users/victim/.ssh/" + "id_rsa"
        fake_etc = "/etc/" + "passwd"
        fake_win = "C:\\Users\\victim\\" + "secret.txt"
        fake_file_url = "file:///tmp/hidden/" + "data.bin"
        fake_auth_header = "Authorization: " + "Bearer abc123"
        fake_tok = "tok" + "-leak"
        fake_bashrc = "/home/user/" + ".bashrc"

        summary = {
            "safe_field": 42,
            "nested": {
                "authorization": fake_bearer,
                "api_key": fake_api_key,
                "chain_of_thought": fake_cot,
                "raw_response": fake_raw,
                "deep": {
                    "password": fake_pw,
                    "env": {"HOME": fake_ssh_path},
                    "absolute_path": fake_etc,
                    "windows_path": fake_win,
                    "file_url": fake_file_url,
                    "bearer_header": fake_auth_header,
                },
            },
            "list_with_secrets": [
                {"token": fake_tok},
                "plain string ok",
                fake_bashrc,
            ],
        }
        return ToolResult(status="completed", evidence_ids=("frame-001",), summary=summary)


@pytest.mark.asyncio
async def test_tool_call_review_redacts_nested_secrets_paths_and_cot(tmp_path: Path) -> None:
    """Malicious nested summaries must never leak into the event ledger."""
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"deterministic-local-video-bytes")

    media = FakeFFmpeg(has_audio=False)
    video_model = FakeVideoModel()
    goal = VideoGoal(objective="Describe what happens in the video")

    decisions = [
        tool_decision("malicious_summary"),
        final_decision("frame-001"),
    ]
    agent_model = ScriptedAgentModel(decisions)

    context: RunContext = RunContext(
        source=VideoSource(path=source_path),
        policy=HarnessPolicy(max_tool_calls=2, max_iterations=1),
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(goal),
        task_model=video_model,
        media=media,
        sampler=AdaptiveSampler(),
        agent_model=agent_model,
        recognizer=None,
    )

    registry = PluginRegistry(allowed_ids=("malicious_summary",))
    registry.register(MaliciousSummaryPlugin())
    registry.resolve()

    kernel = HarnessKernel(policy=AgenticPolicy(), registry=registry)
    await kernel.run(context)

    events = read_events(context.bundle.path)
    completed = _events_of_type(events, "tool.call.completed")
    assert len(completed) == 1
    review = _call_review(completed[0])
    assert review.get("api_version") == CALL_REVIEW_VERSION

    ledger_text = (context.bundle.path / "events.jsonl").read_text(encoding="utf-8")
    forbidden = (
        "sk-secret" + "-token-value",
        "sk-leaked" + "-key-12345",
        "internal reasoning " + "scratchpad text",
        "raw provider " + "body content",
        "hunter" + "2",
        "/Users/victim/.ssh/" + "id_rsa",
        "/etc/" + "passwd",
        "C:\\Users\\victim\\" + "secret.txt",
        "file:///tmp/hidden/" + "data.bin",
        "Authorization: " + "Bearer abc123",
        "tok" + "-leak",
        "/home/user/" + ".bashrc",
    )
    for value in forbidden:
        assert value not in ledger_text, f"forbidden value leaked into events.jsonl: {value!r}"

    summary = review.get("result_summary")
    assert isinstance(summary, dict)
    assert summary.get("safe_field") == 42
    nested = summary.get("nested")
    assert isinstance(nested, dict)
    deep = nested.get("deep")
    assert isinstance(deep, dict)
    assert deep.get("absolute_path") != "/etc/passwd"

    assert review.get("result_evidence_ids") == ["frame-001"]


def test_sanitizer_drops_header_and_message_container_keys() -> None:
    """Headers, request/response bodies, and message containers must be redacted.

    Key normalization must cover hyphenated (X-Api-Key), underscored (api_key),
    and camelCase variants. The entire value of container keys like headers,
    request, response, messages, choices, content is replaced — not recursed into.
    """
    from vidsnap.runtime.call_review import sanitize_review_value

    fake_header_val = "x-secret" + "-header-value"
    fake_msg_content = "system prompt " + "with secrets inside"
    fake_choice_content = "model reply " + "containing secrets"
    fake_req_body = "raw request " + "body payload"
    fake_resp_body = "raw response " + "body payload"

    payload = {
        "safe_field": 42,
        "headers": {"X-Api-Key": fake_header_val, "Content-Type": "application/json"},
        "request": {"messages": [{"role": "user", "content": fake_msg_content}]},
        "response": {"choices": [{"message": {"content": fake_choice_content}}]},
        "messages": [{"role": "system", "content": fake_msg_content}],
        "choices": [{"message": {"content": fake_choice_content}}],
        "content": fake_msg_content,
        "x_api_key": fake_header_val,
        "X-API-KEY": fake_header_val,
        "body": fake_req_body,
        "raw_request": fake_req_body,
        "raw_response": fake_resp_body,
    }

    result = sanitize_review_value(payload)
    assert isinstance(result, dict)

    # Safe fields survive.
    assert result["safe_field"] == 42

    # Container keys must be fully redacted (not recursed).
    assert result["headers"] == "***REDACTED***"
    assert result["request"] == "***REDACTED***"
    assert result["response"] == "***REDACTED***"
    assert result["messages"] == "***REDACTED***"
    assert result["choices"] == "***REDACTED***"
    assert result["content"] == "***REDACTED***"

    # Sensitive key variants must all be redacted.
    assert result["x_api_key"] == "***REDACTED***"
    assert result["X-API-KEY"] == "***REDACTED***"
    assert result["body"] == "***REDACTED***"
    assert result["raw_request"] == "***REDACTED***"
    assert result["raw_response"] == "***REDACTED***"

    # No sensitive values leaked anywhere in the serialized output.
    import json

    serialized = json.dumps(result)
    for val in (
        fake_header_val,
        fake_msg_content,
        fake_choice_content,
        fake_req_body,
        fake_resp_body,
    ):
        assert val not in serialized, f"sensitive value leaked: {val!r}"


def test_sanitizer_redacts_embedded_paths_in_strings() -> None:
    """Absolute paths embedded inside longer strings must be redacted.

    This covers Unix paths (/tmp/...), Windows paths (C:\\...), file:// URLs,
    and signed URL / token query parameters embedded in descriptive text.
    Normal descriptions and numbers must survive.
    """
    from vidsnap.runtime.call_review import sanitize_review_value

    unix_embedded = "cached at /tmp/review-example/" + "private.mp4"
    win_embedded = "saved to C:\\Users\\victim\\" + "docs\\file.txt"
    file_url_embedded = "see file:///var/data/" + "secret.json for details"
    signed_url = "https://cdn.example.com/asset?sig=" + "abc123def456&expires=99999"
    safe_description = "processed 42 frames successfully"
    safe_number = 100

    # P2 counterexamples: paths after non-space boundaries must also be caught.
    paren_unix = "cached at (/tmp/" + "private.mp4)"
    see_file_url = "see(file:///tmp/" + "private.mp4)"
    double_backslash_win = "path is C:\\\\Users\\\\victim\\\\" + "secret.txt"
    forward_slash_win = "cached at C:/Users/" + "private/file.mp4"

    # Safe values that must NOT be redacted.
    safe_asr = "the speaker says hello world"
    safe_vision = "a person walks across the room"
    safe_https = "https://example.com/api/v1/models"

    payload = {
        "note_unix": unix_embedded,
        "note_win": win_embedded,
        "note_file_url": file_url_embedded,
        "note_signed": signed_url,
        "note_paren_unix": paren_unix,
        "note_see_file": see_file_url,
        "note_double_bs_win": double_backslash_win,
        "note_fwd_slash_win": forward_slash_win,
        "description": safe_description,
        "count": safe_number,
        "asr_text": safe_asr,
        "vision_desc": safe_vision,
        "https_url": safe_https,
    }

    result = sanitize_review_value(payload)
    assert isinstance(result, dict)

    # Embedded paths and signed URLs must be redacted.
    assert result["note_unix"] == "***REDACTED***"
    assert result["note_win"] == "***REDACTED***"
    assert result["note_file_url"] == "***REDACTED***"
    assert result["note_signed"] == "***REDACTED***"
    assert result["note_paren_unix"] == "***REDACTED***"
    assert result["note_see_file"] == "***REDACTED***"
    assert result["note_double_bs_win"] == "***REDACTED***"
    assert result["note_fwd_slash_win"] == "***REDACTED***"

    # Safe values survive.
    assert result["description"] == safe_description
    assert result["count"] == safe_number
    assert result["asr_text"] == safe_asr
    assert result["vision_desc"] == safe_vision
    assert result["https_url"] == safe_https
