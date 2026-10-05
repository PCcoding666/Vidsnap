"""Versioned, allow-listed failure records for model requests and runs.

A failure record carries only a fixed category and safe counters. It never
holds exception text, URLs, credentials, headers, or provider response bodies.
Missing measurements stay ``None``: an absent token count means "not reported",
never zero.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, JsonValue, StrictInt

from vidsnap.contracts.models import StrictModel

PROVIDER_FAILURE_SCHEMA = "vidsnap.provider-failure/v1"
RUN_FAILURE_SCHEMA = "vidsnap.run-failure/v1"

FailureCategory = Literal[
    # Transport failures before any HTTP status was received.
    "connect_timeout",
    "read_timeout",
    "write_timeout",
    "pool_timeout",
    "connection_error",
    "transport_error",
    # The provider answered with a non-success HTTP status, by status class.
    "http_4xx",
    "http_5xx",
    "http_other",
    # The provider answered, but not with a usable result.
    "invalid_response",
    # The provider refused before any request: no credential or no model port.
    "provider_unavailable",
    # Any other provider error that carried no structured detail.
    "provider_error",
    # Run control.
    "cancelled",
    "run_deadline",
    "budget_exhausted",
    # A model-requested tool call or final output failed validation.
    "validation",
    # Local media could not be probed or extracted.
    "media_error",
    "unknown",
]


def http_status_category(status: int) -> FailureCategory:
    """Map one non-success HTTP status onto its status-class category."""
    if 400 <= status <= 499:
        return "http_4xx"
    if 500 <= status <= 599:
        return "http_5xx"
    return "http_other"


class ProviderFailure(StrictModel):
    """Structured facts about one failed provider call (``vidsnap.provider-failure/v1``)."""

    model_config = ConfigDict(frozen=True)

    category: FailureCategory
    http_status: StrictInt | None = Field(default=None, ge=100, le=599)
    input_bytes: StrictInt | None = Field(default=None, ge=0)
    input_tokens: StrictInt | None = Field(default=None, ge=0)
    output_tokens: StrictInt | None = Field(default=None, ge=0)

    def as_payload(self) -> dict[str, JsonValue]:
        """Return the versioned trace payload; unmeasured values remain null."""
        return {
            "schema_version": PROVIDER_FAILURE_SCHEMA,
            "category": self.category,
            "http_status": self.http_status,
            "input_bytes": self.input_bytes,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
