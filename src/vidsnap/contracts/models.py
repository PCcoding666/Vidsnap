"""Strict public contracts for grounded video analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base for externally visible contracts that must reject surprise fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TerminalState(str, Enum):
    """Truthful terminal outcomes for a bounded harness run."""

    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    NO_OP = "NO_OP"
    BLOCKED = "BLOCKED"
    EXHAUSTED = "EXHAUSTED"
    FAILED = "FAILED"


class VideoSource(StrictModel):
    """A local video input that the harness may inspect."""

    path: Path
    sha256: str | None = Field(default=None, min_length=64, max_length=64)


class VideoGoal(StrictModel):
    """The narrow, typed goal for one stateless analysis request."""

    objective: str = Field(min_length=1, max_length=4_000)
    required_sections: tuple[str, ...] = ()


class HarnessPolicy(StrictModel):
    """Per-run limits that can only be tighter than the published LoopSpec."""

    max_iterations: int = Field(default=3, ge=1, le=3)
    max_model_calls: int = Field(default=12, ge=0, le=12)
    max_evidence_frames: int = Field(default=96, ge=1, le=96)
    max_wall_seconds: int = Field(default=900, ge=1, le=900)
    output_dir: Path | None = None


class EvidenceReference(StrictModel):
    """A reference to an evidence item retained in a RunBundle."""

    evidence_id: str = Field(min_length=1, max_length=256)


EvidenceModality = Literal["frame", "transcript", "ocr", "audio", "scene"]


class Evidence(StrictModel):
    """A timestamped observation that may support one or more claims."""

    id: str = Field(min_length=1, max_length=256)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    modality: EvidenceModality
    content: str | None = Field(default=None, max_length=100_000)
    artifact_path: Path | None = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_time_range_and_timezone(self) -> Evidence:
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be greater than or equal to start_seconds")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include a UTC timezone")
        if self.captured_at.utcoffset().total_seconds() != 0:
            raise ValueError("captured_at must be expressed in UTC")
        return self


class Claim(StrictModel):
    """A result assertion whose support is explicit and machine-checkable."""

    text: str = Field(min_length=1, max_length=10_000)
    evidence: list[EvidenceReference] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class VideoAnalysisResult(StrictModel):
    """Structured, evidence-grounded output returned by a harness run."""

    summary: str = Field(min_length=1, max_length=20_000)
    claims: list[Claim] = Field(default_factory=list)
    required_sections: dict[str, str] = Field(default_factory=dict)
