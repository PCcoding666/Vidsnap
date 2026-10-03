"""Truth-only projection tests: manifest x RunBundle -> frozen StudioDocument."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vidsnap.studio.manifest import load_studio_manifest
from vidsnap.studio.project import StudioDocument, project_studio
from vidsnap.trace.reader import read_trace


@pytest.fixture
def document(studio_manifest_path: Path) -> StudioDocument:
    return project_studio(studio_manifest_path)


def _trial(document: StudioDocument, version: str, case_id: str, trial_id: str):
    for group in (*document.iteration.eval_cases, *document.iteration.held_out_cases):
        if group.case_id != case_id:
            continue
        for entry in group.entries:
            if entry.version != version:
                continue
            for trial in entry.trials:
                if trial.trial_id == trial_id:
                    return trial
    raise AssertionError(f"trial not projected: {version}/{case_id}/{trial_id}")


def test_api_version_is_studio_projection_v1(document: StudioDocument) -> None:
    assert document.api_version == "vidsnap.studio.projection/v1"


def test_every_trial_is_exact_equivalent_to_direct_read_trace(
    document: StudioDocument, studio_root: Path
) -> None:
    references = [
        ("v0", "case-01", "t1", "runs/v0/case-01/t1"),
        ("v0", "case-01", "t2", "runs/v0/case-01/t2"),
        ("v0", "case-02", "t1", "runs/v0/case-02/t1"),
        ("v1", "case-01", "t1", "runs/v1/case-01/t1"),
    ]
    for version, case_id, trial_id, run in references:
        trial = _trial(document, version, case_id, trial_id)
        expected = read_trace(studio_root / run)
        assert trial.run == run
        assert trial.trace == expected
        assert trial.trace.run_id == expected.run_id
        assert trial.trace.terminal_state == expected.terminal_state
        assert trial.trace.items == expected.items
        assert trial.trace.usage == expected.usage
        assert trial.trace.duration_ms == expected.duration_ms
        assert trial.trace.budget == expected.budget
        assert trial.trace.evidence == expected.evidence
        assert trial.trace.claims == expected.claims
        assert trial.trace.limitations == expected.limitations


def test_same_case_is_grouped_across_versions_and_held_out_is_separate(
    document: StudioDocument,
) -> None:
    assert document.iteration is not None
    eval_groups = {group.case_id: group for group in document.iteration.eval_cases}
    held_out_groups = {group.case_id: group for group in document.iteration.held_out_cases}
    assert set(eval_groups) == {"case-01"}
    assert set(held_out_groups) == {"case-02"}

    grouped = eval_groups["case-01"]
    assert [entry.version for entry in grouped.entries] == ["v0", "v1"]
    assert [len(entry.trials) for entry in grouped.entries] == [2, 1]
    assert grouped.video_sha256 == "a" * 64

    held_out = held_out_groups["case-02"]
    assert [entry.version for entry in held_out.entries] == ["v0"]


def test_safe_manifest_metadata_is_preserved(
    document: StudioDocument, studio_manifest_path: Path
) -> None:
    manifest = load_studio_manifest(studio_manifest_path)
    assert document.title == manifest.title
    assert document.iteration.agent_id == manifest.iteration.agent_id
    assert [version.version for version in document.iteration.versions] == ["v0", "v1"]
    assert [version.summary for version in document.iteration.versions] == [
        "baseline prompt",
        "tightened prompt",
    ]
    assert document.iteration.versions[0].prompt_sha256 == "b" * 64
    assert document.iteration.versions[1].prompt_sha256 is None
    assert document.exploration.problem.statement == manifest.exploration.problem.statement


def test_four_panels_exist_and_project_only_recorded_facts(
    document: StudioDocument,
    studio_root: Path,
    claim_marker: str,
    evidence_marker: str,
) -> None:
    trial = _trial(document, "v0", "case-01", "t1")
    expected = read_trace(studio_root / "runs/v0/case-01/t1")

    assert trial.answer.claims == tuple(expected.claims)
    assert trial.answer.claims[0].text == claim_marker
    assert trial.answer.provenance == "run_bundle"

    assert trial.evidence.items == tuple(expected.evidence)
    assert trial.evidence.items[0].content_preview == evidence_marker
    assert trial.evidence.provenance == "run_bundle"

    assert trial.trace_panel.items == tuple(expected.items)
    for lane_name in ("input", "model", "tools", "verifier"):
        assert getattr(trial.trace_panel.lanes, lane_name) == tuple(
            item for item in expected.items if item.lane == lane_name
        )
    assert trial.trace_panel.budget == expected.budget
    assert trial.trace_panel.duration_ms == expected.duration_ms

    assert trial.verifier.terminal_state == expected.terminal_state
    assert trial.verifier.passed is True
    assert trial.verifier.failed_gates == ()
    assert trial.verifier.provenance == "run_bundle"


def test_unrecorded_fields_stay_none_with_not_recorded_provenance(
    document: StudioDocument,
) -> None:
    trial = _trial(document, "v0", "case-01", "t2")
    assert trial.trace.usage is None
    assert trial.trace.duration_ms is None
    assert trial.trace_panel.duration_ms is None
    assert trial.answer.claims == ()
    assert trial.answer.provenance == "not_recorded"
    assert trial.evidence.items == ()
    assert trial.evidence.provenance == "not_recorded"
    assert trial.verifier.passed is None
    assert trial.verifier.failed_gates is None
    assert trial.verifier.provenance == "not_recorded"
    assert trial.provenance == "run_bundle"


def test_verifier_panel_projects_recorded_gates(document: StudioDocument) -> None:
    trial = _trial(document, "v0", "case-02", "t1")
    assert trial.verifier.passed is False
    assert trial.verifier.failed_gates == ("schema_valid",)


def test_exploration_metrics_use_only_recorded_counts(document: StudioDocument) -> None:
    assert document.exploration is not None
    approaches = {a.id: a for a in document.exploration.approaches}

    full = approaches["full-approach"]
    assert len(full.trials) == 2
    assert full.metrics.passed_trials == 1
    assert full.metrics.violations == 1
    assert full.metrics.tokens == 20
    assert full.metrics.latency_ms == 900

    partial = approaches["partial-approach"]
    assert partial.metrics.passed_trials is None
    assert partial.metrics.violations is None
    assert partial.metrics.tokens is None
    assert partial.metrics.latency_ms == 570


def test_verifier_aggregates_require_every_trial_explicitly_recorded(
    document: StudioDocument,
) -> None:
    assert document.exploration is not None
    approaches = {a.id: a for a in document.exploration.approaches}

    full = approaches["full-approach"]
    assert all(trial.verifier.passed is not None for trial in full.trials)
    assert all(trial.verifier.failed_gates is not None for trial in full.trials)
    assert full.metrics.passed_trials == 1
    assert full.metrics.violations == 1

    partial = approaches["partial-approach"]
    assert any(trial.verifier.passed is None for trial in partial.trials)
    assert any(trial.verifier.failed_gates is None for trial in partial.trials)
    assert partial.metrics.passed_trials is None
    assert partial.metrics.violations is None

    recorded_empty = _trial(document, "v0", "case-01", "t1")
    assert recorded_empty.verifier.failed_gates == ()


def test_document_is_frozen_and_json_round_trips(document: StudioDocument) -> None:
    with pytest.raises(ValueError):
        document.title = "mutated"
    restored = StudioDocument.model_validate_json(document.model_dump_json())
    assert restored == document


def test_serialized_document_carries_no_absolute_paths_or_provider_identity(
    document: StudioDocument, studio_root: Path
) -> None:
    serialized = document.model_dump_json()
    assert str(studio_root) not in serialized
    assert str(studio_root.resolve()) not in serialized
    assert "studio-provider.internal" not in serialized
    assert "provider_reported" in serialized  # usage counters are recorded truth
    for trial_reference in (
        "runs/v0/case-01/t1",
        "runs/v0/case-01/t2",
        "runs/v0/case-02/t1",
        "runs/v1/case-01/t1",
    ):
        assert trial_reference in serialized


def test_projection_is_read_only_over_run_bundles(studio_manifest_path: Path) -> None:
    root = studio_manifest_path.parent
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    project_studio(studio_manifest_path)
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    assert before == after


def test_exploration_trial_panels_match_read_trace(
    document: StudioDocument, studio_root: Path
) -> None:
    approach = next(a for a in document.exploration.approaches if a.id == "full-approach")
    for trial in approach.trials:
        expected = read_trace(studio_root / trial.run)
        assert trial.trace == expected
    assert json.loads(document.model_dump_json())["api_version"] == "vidsnap.studio.projection/v1"


def _completed_tool_names(items) -> tuple[str, ...]:
    return tuple(
        item.payload["name"]
        for item in items
        if item.event_type == "tool.call.completed" and item.lane == "tools"
    )


def test_tools_lane_preserves_distinct_recorded_trajectories(
    document: StudioDocument, studio_root: Path
) -> None:
    full = next(a for a in document.exploration.approaches if a.id == "full-approach")
    trajectories = [
        (_trial(document, "v0", "case-01", "t1"), "runs/v0/case-01/t1", ("transcribe_audio",)),
        (_trial(document, "v1", "case-01", "t1"), "runs/v1/case-01/t1", ("sample_evidence",)),
        (full.trials[0], "runs/exp/full/t1", ("transcribe_audio", "sample_evidence")),
        (full.trials[1], "runs/exp/full/t2", ("sample_evidence", "transcribe_audio")),
    ]
    recorded_trajectories: list[tuple[str, ...]] = []
    for trial, run, expected_tools in trajectories:
        expected = read_trace(studio_root / run)
        expected_tools_lane = tuple(item for item in expected.items if item.lane == "tools")

        assert trial.trace_panel.lanes.tools == expected_tools_lane
        assert trial.trace.items == expected.items
        assert _completed_tool_names(trial.trace_panel.lanes.tools) == expected_tools
        assert _completed_tool_names(expected_tools_lane) == expected_tools
        assert [item.sequence for item in trial.trace_panel.lanes.tools] == [
            item.sequence for item in expected_tools_lane
        ]
        recorded_trajectories.append(_completed_tool_names(trial.trace_panel.lanes.tools))

    assert len(set(recorded_trajectories)) == len(recorded_trajectories)
