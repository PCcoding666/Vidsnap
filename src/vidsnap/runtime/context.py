"""Per-run kernel state that owns evidence accounting and redacted auditing."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Literal, TypeVar

from pydantic import JsonValue

from vidsnap.contracts import Evidence, HarnessPolicy, TerminalState, VideoSource
from vidsnap.contracts.models import StrictModel
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder
from vidsnap.plugins.base import TranscriptionPort
from vidsnap.providers.base import AgentModelPort
from vidsnap.tasks.base import TaskAdapter, TaskVerification
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import MediaProbe
from vidsnap.video.sampling import AdaptiveSampler

OutputT = TypeVar("OutputT", bound=StrictModel)
ModelT = TypeVar("ModelT")


@dataclass(slots=True)
class RunContext(Generic[OutputT, ModelT]):
    """Mutable kernel-owned state for one bounded harness run."""

    source: VideoSource
    policy: HarnessPolicy
    bundle: RunBundle
    task_adapter: TaskAdapter[OutputT, ModelT]
    task_model: ModelT
    media: FFmpegPort
    sampler: AdaptiveSampler
    agent_model: AgentModelPort | None = None
    recognizer: TranscriptionPort | None = None
    result_writer: Callable[[OutputT], object] | None = None
    probe: MediaProbe | None = None
    evidence: list[Evidence] = field(default_factory=list)
    output: OutputT | None = None
    verification: TaskVerification | None = None
    terminal_state: TerminalState | None = None
    tool_result_summaries: list[dict[str, JsonValue]] = field(default_factory=list)
    verifier_feedback: dict[str, JsonValue] | None = None
    call_fingerprints: set[str] = field(default_factory=set)
    format_repair_used: bool = False
    model_calls: int = 0
    tool_calls: int = 0
    iterations: int = 0
    trace: TraceRecorder = field(init=False, repr=False)
    _allocated_ids: set[str] = field(default_factory=set, repr=False)
    _id_counters: dict[str, int] = field(default_factory=dict, repr=False)
    _artifact_calls: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        self.trace = TraceRecorder(self.bundle)

    def next_id(self, prefix: Literal["frame", "transcript"]) -> str:
        """Allocate the next sequential evidence ID for one modality."""
        counter = self._id_counters.get(prefix, 0) + 1
        self._id_counters[prefix] = counter
        evidence_id = f"{prefix}-{counter:03d}"
        self._allocated_ids.add(evidence_id)
        return evidence_id

    def add(self, evidence: Evidence) -> str:
        """Persist one allocated, non-duplicate evidence item and audit it redacted."""
        if evidence.id not in self._allocated_ids:
            raise ValueError(f"evidence id {evidence.id} was not allocated by the kernel")
        if any(item.id == evidence.id for item in self.evidence):
            raise ValueError(f"evidence id {evidence.id} was already added")
        if evidence.artifact_path is not None:
            self._validate_artifact(evidence.artifact_path)
        self.bundle.write_evidence(evidence)
        self.bundle.append_event(
            "evidence.added",
            self._redacted_evidence_payload(evidence),
            event_id=uuid.uuid4().hex,
            event_type="evidence.added",
            status="completed",
        )
        self.evidence.append(evidence)
        return evidence.id

    def next_artifact_dir(self) -> Path:
        """Allocate a unique artifact directory for one sequential tool call."""
        self._artifact_calls += 1
        directory = self.bundle.path / "artifacts" / f"call-{self._artifact_calls:03d}"
        directory.mkdir(parents=True)
        return directory

    def _validate_artifact(self, artifact_path: Path) -> None:
        """Require one existing file beneath this bundle's artifacts directory."""
        artifacts_root = (self.bundle.path / "artifacts").resolve()
        resolved = artifact_path.resolve()
        if not resolved.is_relative_to(artifacts_root):
            raise ValueError(f"evidence artifact must resolve under {artifacts_root}")
        if not resolved.is_file():
            raise ValueError(f"evidence artifact does not exist: {resolved}")

    @staticmethod
    def _redacted_evidence_payload(evidence: Evidence) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "evidence_id": evidence.id,
            "modality": evidence.modality,
            "start_seconds": evidence.start_seconds,
            "end_seconds": evidence.end_seconds,
            "captured_at": evidence.captured_at.isoformat().replace("+00:00", "Z"),
        }
        if evidence.artifact_path is not None and evidence.artifact_path.is_file():
            payload["artifact_bytes"] = evidence.artifact_path.stat().st_size
        return payload
