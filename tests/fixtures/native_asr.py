"""Offline replies shaped like the native DashScope ``qwen-audio-3.1-asr-flash`` response.

``recorded_response()`` is a real reply to a synthetic 7 s clip (request ids removed);
``native_reply()`` builds the smallest reply the client accepts. No network, no media.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RECORDED_RESPONSE = Path(__file__).parent / "asr" / "qwen-audio-3.1-asr-flash-response.json"
RECORDED_TEXT = "今天的作业是第3页第5题，把答案写在练习纸上，明天早上交。"
ASR_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def recorded_response() -> dict[str, Any]:
    """The recorded reply: ``output.text``, ``output.sentence`` with words, and ``usage``."""
    parsed = json.loads(RECORDED_RESPONSE.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def native_reply(
    text: str,
    *,
    duration: int | None = 1,
    input_tokens: int | None = 30,
    output_tokens: int | None = 5,
) -> dict[str, Any]:
    """A minimal reply: ``output.text`` plus ``usage`` (a counter set to ``None`` is omitted)."""
    usage: dict[str, int] = {}
    if duration is not None:
        usage["duration"] = duration
    if input_tokens is not None:
        usage["input_tokens"] = input_tokens
    if output_tokens is not None:
        usage["output_tokens"] = output_tokens
    if input_tokens is not None and output_tokens is not None:
        usage["total_tokens"] = input_tokens + output_tokens
    return {"output": {"text": text}, "usage": usage}


def audio_part(request_body: dict[str, Any]) -> dict[str, Any]:
    """The single ``input_audio`` part of a recorded native request body."""
    (message,) = request_body["input"]["messages"]
    (part,) = message["content"]
    assert isinstance(part, dict)
    return part
