"""Read-only projection of a studio manifest and its RunBundles into one document.

``project_studio`` is the single truth boundary for the Eval Studio workbench:
it loads the pre-registered manifest, projects every referenced RunBundle with
``vidsnap.trace.read_trace``, and freezes the result into a ``StudioDocument``.
Nothing is invented: missing values stay ``None`` and surface as "not
recorded" downstream; provenance is only ``manifest``, ``run_bundle``, or
``not_recorded``. The projection never writes, never touches the network, and
never reads media or artifact bytes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, JsonValue

from vidsnap.studio.manifest import (
    ApproachHarness,
    StudioExploration,
    StudioIteration,
    StudioProblem,
    StudioTrial,
    load_studio_manifest,
)
from vidsnap.trace.models import (
    FrozenProjectionModel,
    TraceBudget,
    TraceClaim,
    TraceDocument,
    TraceEvidence,
    TraceItem,
)
from vidsnap.trace.reader import _redact_string, read_trace

StudioProvenance = Literal["manifest", "run_bundle", "not_recorded"]

_PLACEHOLDER = "***REDACTED***"
_ABSOLUTE_PATH_PATTERN = re.compile(
    r"/(?:Users|home|private|var|tmp|Volumes)/[^\s\"']*"
    r"|\b[A-Za-z]:\\[^\s\"']*"
    r"|\\\\[^\s\"'/]+(?:\\[^\s\"']*)?"
)
_EXCLUDED_PAYLOAD_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "auth_header",
        "base_url",
        "baseurl",
        "chain_of_thought",
        "cookie",
        "internal_reasoning",
        "password",
        "provider_id",
        "provider_identity",
        "provider_response",
        "raw_request",
        "raw_response",
        "scratchpad",
        "secret",
    }
)


class StudioAnswerPanel(FrozenProjectionModel):
    """The Answer panel: structured claims projected from ``result.json`` only."""

    claims: tuple[TraceClaim, ...] = ()
    provenance: StudioProvenance = "not_recorded"


class StudioEvidencePanel(FrozenProjectionModel):
    """The Evidence panel: structured evidence items, never artifact bytes."""

    items: tuple[TraceEvidence, ...] = ()
    provenance: StudioProvenance = "not_recorded"


class StudioLaneSet(FrozenProjectionModel):
    """Recorded trace items grouped by their Input/Model/Tools/Verifier lanes."""

    input: tuple[TraceItem, ...] = ()
    model: tuple[TraceItem, ...] = ()
    tools: tuple[TraceItem, ...] = ()
    verifier: tuple[TraceItem, ...] = ()


class StudioTracePanel(FrozenProjectionModel):
    """The Trace panel: recorded event sequence, budget counters, and duration."""

    items: tuple[TraceItem, ...] = ()
    lanes: StudioLaneSet = Field(default_factory=StudioLaneSet)
    budget: TraceBudget = Field(default_factory=TraceBudget)
    duration_ms: int | None = Field(default=None, ge=0)


class StudioVerifierPanel(FrozenProjectionModel):
    """The Verifier panel: recorded gates and terminal state, never inferred.

    ``failed_gates`` is ``None`` when no gate list was recorded and an empty
    tuple when a gate list was explicitly recorded as empty.
    """

    terminal_state: str | None = None
    passed: bool | None = None
    failed_gates: tuple[str, ...] | None = None
    provenance: StudioProvenance = "not_recorded"


class StudioTrialProjection(FrozenProjectionModel):
    """One trial: the exact ``read_trace`` projection plus its four panels."""

    trial_id: str = Field(min_length=1, max_length=256)
    run: str = Field(min_length=1, max_length=4_096)
    provenance: StudioProvenance = "run_bundle"
    trace: TraceDocument
    answer: StudioAnswerPanel = Field(default_factory=StudioAnswerPanel)
    evidence: StudioEvidencePanel = Field(default_factory=StudioEvidencePanel)
    trace_panel: StudioTracePanel = Field(default_factory=StudioTracePanel)
    verifier: StudioVerifierPanel = Field(default_factory=StudioVerifierPanel)


class StudioCaseVersionEntry(FrozenProjectionModel):
    """The trials one prompt version recorded for one case."""

    version: str = Field(min_length=1, max_length=64)
    trials: tuple[StudioTrialProjection, ...]


class StudioCaseGroup(FrozenProjectionModel):
    """One case grouped across versions, with only safe manifest metadata."""

    case_id: str = Field(min_length=1, max_length=256)
    held_out: bool = False
    video_sha256: str | None = None
    entries: tuple[StudioCaseVersionEntry, ...]


class StudioVersionProjection(FrozenProjectionModel):
    """Safe pre-registered metadata for one prompt version."""

    version: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=10_000)
    prompt: str | None = Field(default=None, max_length=100_000)
    prompt_sha256: str | None = None


class StudioIterationProjection(FrozenProjectionModel):
    """The iteration workspace: versions plus case groups, held-out separate."""

    agent_id: str = Field(min_length=1, max_length=256)
    versions: tuple[StudioVersionProjection, ...]
    eval_cases: tuple[StudioCaseGroup, ...] = ()
    held_out_cases: tuple[StudioCaseGroup, ...] = ()


class StudioApproachMetrics(FrozenProjectionModel):
    """Comparison metrics projected only from recorded counts; None = not recorded.

    ``passed_trials`` and ``violations`` aggregate only when every compared
    trial explicitly recorded the underlying verifier facts.
    """

    passed_trials: int | None = Field(default=None, ge=0)
    violations: int | None = Field(default=None, ge=0)
    tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)


class StudioApproachProjection(FrozenProjectionModel):
    """One exploration approach with its trials and recorded-only metrics."""

    id: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=256)
    synthetic: bool = False
    prompt_sha256: str | None = None
    harness: ApproachHarness
    trials: tuple[StudioTrialProjection, ...]
    metrics: StudioApproachMetrics = Field(default_factory=StudioApproachMetrics)


class StudioExplorationProjection(FrozenProjectionModel):
    """The exploration workspace: one problem and its compared approaches."""

    problem: StudioProblem
    approaches: tuple[StudioApproachProjection, ...]


class StudioDocument(FrozenProjectionModel):
    """The frozen, redacted Eval Studio projection (embedded in the export)."""

    api_version: Literal["vidsnap.studio.projection/v1"] = "vidsnap.studio.projection/v1"
    title: str | None = Field(default=None, max_length=1_000)
    iteration: StudioIterationProjection | None = None
    exploration: StudioExplorationProjection | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        dumped = super().model_dump(**kwargs)
        assert isinstance(dumped, dict)
        scrubbed = _scrub_value(dumped)
        assert isinstance(scrubbed, dict)
        return scrubbed

    def model_dump_json(self, **kwargs: Any) -> str:
        kwargs["mode"] = "json"
        return json.dumps(self.model_dump(**kwargs), ensure_ascii=True)


def project_studio(manifest_path: Path | str) -> StudioDocument:
    """Project a validated manifest and its RunBundles into a frozen document."""
    manifest = load_studio_manifest(manifest_path)
    root = Path(manifest_path).parent.resolve()
    iteration = (
        _project_iteration(root, manifest.iteration) if manifest.iteration is not None else None
    )
    exploration = (
        _project_exploration(root, manifest.exploration)
        if manifest.exploration is not None
        else None
    )
    return StudioDocument(
        title=_sanitize_manifest_text(manifest.title) if manifest.title is not None else None,
        iteration=iteration,
        exploration=exploration,
    )


def _project_iteration(root: Path, iteration: StudioIteration) -> StudioIterationProjection:
    versions = tuple(
        StudioVersionProjection(
            version=version.version,
            summary=_sanitize_manifest_text(version.summary),
            prompt=(
                _sanitize_manifest_text(version.prompt) if version.prompt is not None else None
            ),
            prompt_sha256=version.prompt_sha256,
        )
        for version in iteration.versions
    )
    eval_groups: dict[str, list[StudioCaseVersionEntry]] = {}
    eval_meta: dict[str, str | None] = {}
    held_out_groups: dict[str, list[StudioCaseVersionEntry]] = {}
    held_out_meta: dict[str, str | None] = {}
    for version in iteration.versions:
        for case in version.cases:
            entry = StudioCaseVersionEntry(
                version=version.version,
                trials=tuple(_project_trial(root, trial) for trial in case.trials),
            )
            if case.held_out:
                held_out_groups.setdefault(case.case_id, []).append(entry)
                held_out_meta.setdefault(case.case_id, case.video_sha256)
            else:
                eval_groups.setdefault(case.case_id, []).append(entry)
                eval_meta.setdefault(case.case_id, case.video_sha256)
    return StudioIterationProjection(
        agent_id=_sanitize_manifest_text(iteration.agent_id),
        versions=versions,
        eval_cases=tuple(
            StudioCaseGroup(
                case_id=case_id,
                held_out=False,
                video_sha256=eval_meta[case_id],
                entries=tuple(entries),
            )
            for case_id, entries in eval_groups.items()
        ),
        held_out_cases=tuple(
            StudioCaseGroup(
                case_id=case_id,
                held_out=True,
                video_sha256=held_out_meta[case_id],
                entries=tuple(entries),
            )
            for case_id, entries in held_out_groups.items()
        ),
    )


def _project_exploration(root: Path, exploration: StudioExploration) -> StudioExplorationProjection:
    approaches = tuple(
        StudioApproachProjection(
            id=approach.id,
            label=_sanitize_manifest_text(approach.label),
            synthetic=approach.synthetic,
            prompt_sha256=approach.prompt_sha256,
            harness=approach.harness,
            trials=(trials := tuple(_project_trial(root, trial) for trial in approach.trials)),
            metrics=_approach_metrics(trials),
        )
        for approach in exploration.approaches
    )
    return StudioExplorationProjection(
        problem=StudioProblem(
            statement=_sanitize_manifest_text(exploration.problem.statement),
            constraints=tuple(
                _sanitize_manifest_text(constraint)
                for constraint in exploration.problem.constraints
            ),
        ),
        approaches=approaches,
    )


def _project_trial(root: Path, trial: StudioTrial) -> StudioTrialProjection:
    bundle_dir = (root / trial.run).resolve()
    _check_bundle_containment(bundle_dir)
    trace = read_trace(bundle_dir)
    return StudioTrialProjection(
        trial_id=trial.trial_id,
        run=trial.run,
        provenance="run_bundle",
        trace=trace,
        answer=StudioAnswerPanel(
            claims=tuple(trace.claims),
            provenance="run_bundle" if trace.claims else "not_recorded",
        ),
        evidence=StudioEvidencePanel(
            items=tuple(trace.evidence),
            provenance="run_bundle" if trace.evidence else "not_recorded",
        ),
        trace_panel=StudioTracePanel(
            items=tuple(trace.items),
            lanes=StudioLaneSet(
                input=tuple(item for item in trace.items if item.lane == "input"),
                model=tuple(item for item in trace.items if item.lane == "model"),
                tools=tuple(item for item in trace.items if item.lane == "tools"),
                verifier=tuple(item for item in trace.items if item.lane == "verifier"),
            ),
            budget=trace.budget,
            duration_ms=trace.duration_ms,
        ),
        verifier=_verifier_panel(trace),
    )


_BUNDLE_MEMBER_NAMES = ("events.jsonl", "outcomes.jsonl", "result.json")


def _check_bundle_containment(bundle_dir: Path) -> None:
    """Refuse bundle members that resolve outside the run directory.

    Missing optional members keep the existing read_trace behavior; only a
    member that escapes the bundle (for example via a symlink) is rejected,
    and the failure message never carries a path.
    """
    for name in _BUNDLE_MEMBER_NAMES:
        _check_member_containment(bundle_dir, bundle_dir / name)
    evidence_dir = bundle_dir / "evidence"
    if evidence_dir.exists() or evidence_dir.is_symlink():
        _check_member_containment(bundle_dir, evidence_dir)
        for candidate in sorted(evidence_dir.glob("*.json")):
            _check_member_containment(bundle_dir, candidate)


def _check_member_containment(bundle_dir: Path, member: Path) -> None:
    if not member.exists() and not member.is_symlink():
        return
    try:
        resolved = member.resolve()
    except OSError:
        raise ValueError("run bundle member is unresolvable") from None
    if not resolved.is_relative_to(bundle_dir):
        raise ValueError("run bundle member escapes its run directory")


def _verifier_panel(trace: TraceDocument) -> StudioVerifierPanel:
    verifier_items = tuple(item for item in trace.items if item.lane == "verifier")
    recorded = [
        item
        for item in trace.items
        if item.event_type == "verifier.completed" and item.status == "completed"
    ]
    gate_lists: list[list[str]] = []
    for item in verifier_items:
        raw_gates = item.payload.get("failed_gates")
        if isinstance(raw_gates, list):
            gate_lists.append([gate for gate in raw_gates if isinstance(gate, str)])
    failed_gates: tuple[str, ...] | None = None
    if gate_lists:
        collected: list[str] = []
        for gate_names in gate_lists:
            collected.extend(gate_names)
        failed_gates = tuple(collected)
    passed: bool | None = None
    if recorded:
        last = recorded[-1].payload.get("passed")
        passed = last if isinstance(last, bool) else None
    return StudioVerifierPanel(
        terminal_state=trace.terminal_state,
        passed=passed,
        failed_gates=failed_gates,
        provenance="run_bundle" if verifier_items else "not_recorded",
    )


def _approach_metrics(trials: tuple[StudioTrialProjection, ...]) -> StudioApproachMetrics:
    passed_values = [trial.verifier.passed for trial in trials]
    passed_trials: int | None = None
    if all(value is not None for value in passed_values):
        passed_trials = sum(1 for value in passed_values if value is True)
    gate_values = [trial.verifier.failed_gates for trial in trials]
    violations: int | None = None
    if all(gates is not None for gates in gate_values):
        violations = sum(len(gates) for gates in gate_values if gates is not None)
    tokens: int | None = None
    usages = [trial.trace.usage for trial in trials]
    if usages and all(usage is not None and usage.provider_reported for usage in usages):
        tokens = sum(
            usage.input_tokens + usage.output_tokens for usage in usages if usage is not None
        )
    durations = [trial.trace.duration_ms for trial in trials]
    latency_ms: int | None = None
    if durations and all(duration is not None for duration in durations):
        latency_ms = sum(duration for duration in durations if duration is not None)
    return StudioApproachMetrics(
        passed_trials=passed_trials,
        violations=violations,
        tokens=tokens,
        latency_ms=latency_ms,
    )


def _sanitize_manifest_text(value: str) -> str:
    """Apply the trace string rules plus absolute-path stripping to manifest text."""
    stripped = _ABSOLUTE_PATH_PATTERN.sub(_PLACEHOLDER, value)
    return _redact_string(stripped)


def _scrub_value(value: JsonValue) -> JsonValue:
    """Serialization-boundary scrub: drop excluded keys and exposed strings."""
    if isinstance(value, dict):
        scrubbed: dict[str, JsonValue] = {}
        for key, item in value.items():
            if str(key).lower() in _EXCLUDED_PAYLOAD_KEYS:
                continue
            scrubbed[str(key)] = _scrub_value(item)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_manifest_text(value)
    return value
