"""Fair request preparation for Direct and evidence-harness benchmark variants."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from vidsnap.contracts import TerminalState

BenchmarkVariant = Literal["direct", "direct_asr", "harness_visual", "harness_full"]


@dataclass(frozen=True, slots=True)
class Transcript:
    """One shared transcript object, including its local provenance hash."""

    text: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class VideoRequest:
    """A fully specified Direct baseline request; fps is never implicit."""

    source: Path
    fps: int
    transcript: Transcript | None
    variant: BenchmarkVariant


@dataclass(frozen=True, slots=True)
class EvidenceRequest:
    """A fully specified Harness request that may share the exact transcript object."""

    source: Path
    transcript: Transcript | None
    variant: BenchmarkVariant


class BenchmarkModelPort(Protocol):
    """Minimal adapter implemented by live and fake benchmark model clients."""

    def prepare_video(self, request: VideoRequest) -> None:
        """Accept a full-video request for the Direct baseline."""

    def prepare_evidence(self, request: EvidenceRequest) -> None:
        """Accept a Harness evidence-pack request."""


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """A task with only local source path and external dataset provenance."""

    case_id: str
    source: Path
    goal: str
    dataset_license: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """One recorded comparison outcome, including truthful terminal status."""

    case_id: str
    variant: BenchmarkVariant
    terminal_state: TerminalState
    metrics: dict[str, float] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    evidence_frames: int = 0
    input_bytes: int = 0
    latency_seconds: float = 0.0
    credits: float | None = None


class DirectRunner:
    """Prepare the fixed Direct baseline with complete video and exactly two fps."""

    def __init__(self, *, model: BenchmarkModelPort) -> None:
        self.model = model

    def prepare(self, source: Path, transcript: Transcript | None) -> VideoRequest:
        """Create and submit a Direct or Direct+ASR request with fixed fps=2."""
        request = VideoRequest(
            source=source,
            fps=2,
            transcript=transcript,
            variant="direct_asr" if transcript is not None else "direct",
        )
        self.model.prepare_video(request)
        return request


class HarnessRunner:
    """Prepare Harness-Visual or Harness-Full requests without changing transcript identity."""

    def __init__(self, *, model: BenchmarkModelPort) -> None:
        self.model = model

    def prepare(self, source: Path, transcript: Transcript | None) -> EvidenceRequest:
        """Create and submit a Harness request sharing the caller-supplied transcript object."""
        request = EvidenceRequest(
            source=source,
            transcript=transcript,
            variant="harness_full" if transcript is not None else "harness_visual",
        )
        self.model.prepare_evidence(request)
        return request


def compare_results(
    direct: list[BenchmarkResult],
    harness: list[BenchmarkResult],
    *,
    quality_metric: str = "fact_f1",
) -> str:
    """Return an honest status; no unmeasured benchmark may claim superiority."""
    if not direct or not harness:
        return "NOT_YET_SUPERIOR"
    direct_values = [
        result.metrics[quality_metric] for result in direct if quality_metric in result.metrics
    ]
    harness_values = [
        result.metrics[quality_metric] for result in harness if quality_metric in result.metrics
    ]
    if not direct_values or not harness_values:
        return "NOT_YET_SUPERIOR"
    return (
        "HARNESS_SUPERIOR"
        if sum(harness_values) / len(harness_values) > sum(direct_values) / len(direct_values)
        else "NOT_YET_SUPERIOR"
    )
