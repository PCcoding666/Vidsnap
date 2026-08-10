"""Typed, append-only events for a single harness run."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import Field, JsonValue, model_validator

from vidsnap.contracts.models import StrictModel


class RunEvent(StrictModel):
    """One timestamped state transition or observation in a RunBundle."""

    sequence: int = Field(ge=1)
    phase: str = Field(min_length=1, max_length=128)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def require_utc_timestamp(self) -> RunEvent:
        utc_offset = self.occurred_at.utcoffset()
        if self.occurred_at.tzinfo is None or utc_offset is None:
            raise ValueError("occurred_at must include a UTC timezone")
        if utc_offset.total_seconds() != 0:
            raise ValueError("occurred_at must be expressed in UTC")
        return self

    def to_json(self) -> str:
        """Serialize the event deterministically for a JSONL ledger."""
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
