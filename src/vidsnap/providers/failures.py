"""Map built-in provider HTTP outcomes onto allow-listed failure records."""

from __future__ import annotations

import json
from collections.abc import Mapping

import httpx

from vidsnap.contracts.failures import FailureCategory, ProviderFailure, http_status_category


def request_body_bytes(request_payload: Mapping[str, object]) -> int:
    """Size of the request body as compact ASCII JSON, measured before sending."""
    return len(
        json.dumps(request_payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    )


def reported_token_counts(payload: object) -> tuple[int | None, int | None]:
    """Return only valid non-negative ``prompt``/``completion`` token counters."""
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return None, None
    return _counter(usage.get("prompt_tokens")), _counter(usage.get("completion_tokens"))


def http_failure(error: httpx.HTTPError, *, input_bytes: int | None) -> ProviderFailure:
    """Categorize one httpx failure; never retain its text, URL, or body."""
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        try:
            prompt_tokens, completion_tokens = reported_token_counts(error.response.json())
        except (ValueError, RecursionError):
            prompt_tokens, completion_tokens = None, None
        return ProviderFailure(
            category=http_status_category(status),
            http_status=status if 100 <= status <= 599 else None,
            input_bytes=input_bytes,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
    category: FailureCategory
    if isinstance(error, httpx.ConnectTimeout):
        category = "connect_timeout"
    elif isinstance(error, httpx.ReadTimeout):
        category = "read_timeout"
    elif isinstance(error, httpx.WriteTimeout):
        category = "write_timeout"
    elif isinstance(error, httpx.PoolTimeout):
        category = "pool_timeout"
    elif isinstance(error, httpx.ConnectError):
        category = "connection_error"
    else:
        category = "transport_error"
    return ProviderFailure(category=category, input_bytes=input_bytes)


def invalid_response_failure(payload: object, *, input_bytes: int | None) -> ProviderFailure:
    """Describe a received but unusable response, keeping any valid usage counters."""
    prompt_tokens, completion_tokens = reported_token_counts(payload)
    return ProviderFailure(
        category="invalid_response",
        input_bytes=input_bytes,
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
    )


def _counter(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None
