"""Pre-registered, deterministic statistics for the internal MCQ benchmark."""

from __future__ import annotations

import math
import random
import re
from collections.abc import Sequence, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from vidsnap.contracts import AcquisitionTool, ToolPlan
from vidsnap.contracts.models import StrictModel

BenchmarkConclusion = Literal["HARNESS_SUPERIOR", "NOT_YET_SUPERIOR"]
DatasetName = Literal["Video-MME", "MVBench"]
DurationStratum = Literal["short", "medium", "long"]
EvidenceRequirement = Literal["visual", "speech", "temporal"]


class FormalCase(StrictModel):
    """One fully registered local MCQ case with dataset provenance."""

    case_id: str = Field(min_length=1, max_length=256)
    dataset: DatasetName
    dataset_version: str = Field(min_length=1, max_length=256)
    dataset_license: str = Field(min_length=1, max_length=4_000)
    source_url: str = Field(min_length=1, max_length=2_000)
    source: Path
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    question: str = Field(min_length=1, max_length=8_000)
    options: dict[str, str] = Field(min_length=2, max_length=8)
    answer: str = Field(min_length=1, max_length=1)
    subtitle_path: Path | None = None
    has_audio: bool
    duration_stratum: DurationStratum
    requirements: tuple[EvidenceRequirement, ...] = Field(min_length=1, max_length=3)
    expected_tools: tuple[AcquisitionTool, ...] = Field(max_length=2)

    @model_validator(mode="after")
    def validate_mcq_and_tools(self) -> FormalCase:
        labels = tuple(sorted(self.options))
        if any(label not in tuple("ABCDEFGH") for label in labels):
            raise ValueError("option labels must be uppercase letters A through H")
        if any(not text.strip() for text in self.options.values()):
            raise ValueError("option text must not be empty")
        if self.answer not in self.options:
            raise ValueError("answer must identify one declared option")
        if len(set(self.requirements)) != len(self.requirements):
            raise ValueError("evidence requirements must be unique")
        ToolPlan(tools=self.expected_tools)
        return self

    @property
    def option_labels(self) -> tuple[str, ...]:
        """Return deterministic labels for exact-answer parsing."""
        return tuple(sorted(self.options))


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    """A paired point estimate and percentile confidence interval."""

    point_estimate: float
    lower: float
    upper: float
    confidence: float = 0.95


@dataclass(frozen=True, slots=True)
class ToolSelectionScore:
    """Micro tool-choice quality plus per-case misuse rates."""

    precision: float
    recall: float
    f1: float
    invalid_calls: int
    missed_calls: int
    invalid_call_rate: float
    missed_call_rate: float


def parse_mcq_answer(response: str, option_labels: Sequence[str]) -> str | None:
    """Parse one declared answer letter without semantic or model-based judging."""
    labels = tuple(label.strip().upper() for label in option_labels)
    if not labels or len(labels) != len(set(labels)) or any(len(label) != 1 for label in labels):
        raise ValueError("option labels must be unique single letters")
    normalized = response.strip().upper()
    if normalized in labels:
        return normalized
    match = re.fullmatch(
        r"(?:THE\s+)?BEST\s+ANSWER\s+IS\s*:?\s*\(?([A-Z])\)?[.!]?",
        normalized,
    )
    if match is None or match.group(1) not in labels:
        return None
    return match.group(1)


def paired_bootstrap_delta(
    fixed: Sequence[int],
    agentic: Sequence[int],
    *,
    seed: int,
    resamples: int = 10_000,
) -> BootstrapInterval:
    """Estimate Agentic-minus-Fixed accuracy using paired case resampling."""
    if not fixed or len(fixed) != len(agentic):
        raise ValueError("paired outcomes must have the same non-zero length")
    if any(value not in {0, 1} for value in (*fixed, *agentic)):
        raise ValueError("paired outcomes must be binary")
    if resamples < 1:
        raise ValueError("resamples must be positive")

    differences = [
        agentic_value - fixed_value for fixed_value, agentic_value in zip(fixed, agentic)
    ]
    point_estimate = sum(differences) / len(differences)
    generator = random.Random(seed)
    estimates = sorted(
        sum(differences[generator.randrange(len(differences))] for _ in differences)
        / len(differences)
        for _ in range(resamples)
    )
    lower_index = max(0, math.floor(0.025 * resamples))
    upper_index = min(resamples - 1, math.ceil(0.975 * resamples) - 1)
    return BootstrapInterval(
        point_estimate=point_estimate,
        lower=estimates[lower_index],
        upper=estimates[upper_index],
    )


def superiority_status(interval: BootstrapInterval) -> BenchmarkConclusion:
    """Apply the registered strict-positive lower-bound conclusion rule."""
    return "HARNESS_SUPERIOR" if interval.lower > 0 else "NOT_YET_SUPERIOR"


def tool_selection_score(
    predicted: Sequence[Set[AcquisitionTool]],
    expected: Sequence[Set[AcquisitionTool]],
) -> ToolSelectionScore:
    """Compute micro tool precision/recall/F1 and per-case error rates."""
    if not predicted or len(predicted) != len(expected):
        raise ValueError("tool decisions must have the same non-zero length")
    true_positive = sum(len(left & right) for left, right in zip(predicted, expected))
    invalid_calls = sum(len(left - right) for left, right in zip(predicted, expected))
    missed_calls = sum(len(right - left) for left, right in zip(predicted, expected))
    predicted_count = true_positive + invalid_calls
    expected_count = true_positive + missed_calls
    precision = true_positive / predicted_count if predicted_count else float(expected_count == 0)
    recall = true_positive / expected_count if expected_count else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    case_count = len(predicted)
    return ToolSelectionScore(
        precision=precision,
        recall=recall,
        f1=f1,
        invalid_calls=invalid_calls,
        missed_calls=missed_calls,
        invalid_call_rate=invalid_calls / case_count,
        missed_call_rate=missed_calls / case_count,
    )
