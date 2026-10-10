"""Versioned call-review metadata for real tool and model executions.

Provides a recursive sanitizer and builders for the vidsnap.call-review/v1
payload attached to tool.call and model.request events. The sanitizer redacts
sensitive keys, absolute paths, and secret-bearing strings while preserving
safe usage counters and non-sensitive structure.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from pydantic import JsonValue

if TYPE_CHECKING:
    from vidsnap.contracts import Evidence

CALL_REVIEW_API_VERSION = "vidsnap.call-review/v1"

_REDACTED = "***REDACTED***"

# Unix absolute path: at start of string, or after a non-word, non-colon,
# non-slash character (covers space, paren, quote, CJK punctuation, etc.).
_UNIX_PATH_RE = re.compile(r"(?:^|(?<=[^\w:/]))/[^\s]")

# file:// URL anywhere in the string.
_FILE_URL_RE = re.compile(r"file://", re.IGNORECASE)

# Windows drive path: letter + colon followed by a slash or backslash,
# anywhere in the string.  Covers C:\, C:\\, and C:/ variants.
# The \b prevents matching inside scheme:// URLs (e.g. https://).
_WIN_PATH_RE = re.compile(r"(?<!\w)[A-Za-z]:[/\\]")

_CREDENTIAL_RE = re.compile(
    r"(?:bearer\s|authorization:|api_key=)",
    re.IGNORECASE,
)

_SIGNED_PARAM_RE = re.compile(
    r"\?(?:[^#\s]*&)?(?:sig|signature|token|key|credential)=",
    re.IGNORECASE,
)

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "chain_of_thought",
    "internal_reasoning",
    "scratchpad",
    "thought",
    "reasoning",
    "raw",
    "body",
)

_SENSITIVE_EXACT_KEYS = frozenset({"env", "environ", "environment", "cot"})

_CONTAINER_KEYS = frozenset({"headers", "request", "response", "messages", "choices", "content"})

_SAFE_USAGE_COUNTERS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
    }
)


def sanitize_review_value(value: JsonValue) -> JsonValue:
    """Recursively redact secrets, absolute paths, and CoT from a JSON value."""
    if isinstance(value, dict):
        return _sanitize_dict(value)
    if isinstance(value, list):
        return [sanitize_review_value(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def tool_start_review(parameters: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Build the call_review payload for a tool.call.started event."""
    return {
        "api_version": CALL_REVIEW_API_VERSION,
        "parameters": sanitize_review_value(dict(parameters)),
    }


def tool_result_review(
    evidence_ids: tuple[str, ...],
    summary: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    """Build the call_review payload for a tool.call.completed event."""
    return {
        "api_version": CALL_REVIEW_API_VERSION,
        "result_evidence_ids": list(evidence_ids),
        "result_summary": sanitize_review_value(dict(summary)),
    }


def _sanitize_dict(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    cleaned: dict[str, JsonValue] = {}
    for key, item in value.items():
        normalized = key.lower()
        if normalized in _SAFE_USAGE_COUNTERS and _is_safe_counter(item):
            cleaned[key] = item
            continue
        if normalized in _CONTAINER_KEYS:
            cleaned[key] = _REDACTED
            continue
        underscored = normalized.replace("-", "_")
        if _is_sensitive_key(underscored):
            cleaned[key] = _REDACTED
            continue
        cleaned[key] = sanitize_review_value(item)
    return cleaned


def _is_sensitive_key(normalized: str) -> bool:
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _is_safe_counter(value: JsonValue) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _redact_string(value: str) -> str:
    if not value:
        return value
    if _UNIX_PATH_RE.search(value):
        return _REDACTED
    if _FILE_URL_RE.search(value):
        return _REDACTED
    if _WIN_PATH_RE.search(value):
        return _REDACTED
    if _CREDENTIAL_RE.search(value):
        return _REDACTED
    if _SIGNED_PARAM_RE.search(value):
        return _REDACTED
    return value


_POLICY_CONTROL_MODES: dict[str, str] = {
    "FixedPolicy": "fixed",
    "DirectPolicy": "direct",
    "AgenticPolicy": "agentic",
}


def evidence_snapshot(evidence: Sequence[Evidence]) -> list[JsonValue]:
    """Build a read-only snapshot of evidence items for model request review.

    Records only id, modality, time bounds, and content length. Never includes
    raw content, artifact paths, or base64 data.
    """
    items: list[JsonValue] = []
    for item in evidence:
        entry: dict[str, JsonValue] = {
            "evidence_id": item.id,
            "modality": item.modality,
            "start_seconds": item.start_seconds,
            "end_seconds": item.end_seconds,
            "content_chars": len(item.content) if item.content is not None else 0,
        }
        items.append(entry)
    return items


def model_request_review(
    *,
    policy_name: str,
    evidence: Sequence[Evidence],
    request_kind: str,
    tool_results: Sequence[Mapping[str, JsonValue]] | None = None,
    format_repair: bool | None = None,
    verifier_feedback: Mapping[str, JsonValue] | None = None,
    remaining_model_calls: int | None = None,
    remaining_tool_calls: int | None = None,
    remaining_frames: int | None = None,
) -> dict[str, JsonValue]:
    """Build the call_review payload for a model.request.started event."""
    control_mode = _POLICY_CONTROL_MODES.get(policy_name)
    review: dict[str, JsonValue] = {
        "api_version": CALL_REVIEW_API_VERSION,
        "control_mode": control_mode,
        "request_kind": request_kind,
        "input_evidence": evidence_snapshot(evidence),
        "decision_explanation": None,
    }
    if request_kind == "agent_decision":
        review["tool_results"] = (
            [sanitize_review_value(dict(tr)) for tr in tool_results]
            if tool_results is not None
            else []
        )
        review["format_repair"] = format_repair if format_repair is not None else False
        review["verifier_feedback"] = (
            sanitize_review_value(dict(verifier_feedback))
            if verifier_feedback is not None
            else None
        )
        if remaining_model_calls is not None:
            review["remaining_model_calls"] = remaining_model_calls
        if remaining_tool_calls is not None:
            review["remaining_tool_calls"] = remaining_tool_calls
        if remaining_frames is not None:
            review["remaining_frames"] = remaining_frames
    return review
