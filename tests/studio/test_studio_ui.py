"""Static structural and accessibility assertions over the exported HTML."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from vidsnap.contracts import TerminalState, default_loop_spec
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.trace_recorder import TraceRecorder
from vidsnap.studio.export import export_studio
from vidsnap.trace.reader import read_trace

DATA_SCRIPT_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.DOTALL)


@pytest.fixture
def exported_html(studio_manifest_path: Path, tmp_path: Path) -> str:
    output = tmp_path / "ui" / "eval-studio.html"
    export_studio(studio_manifest_path, output)
    return output.read_text(encoding="utf-8")


def test_workspace_tabs_use_real_tablist_roles_and_initial_state(exported_html: str) -> None:
    assert exported_html.count('role="tablist"') >= 3
    assert exported_html.count('role="tab"') >= 6
    assert exported_html.count('role="tabpanel"') >= 6
    assert 'aria-selected="true"' in exported_html
    assert 'aria-selected="false"' in exported_html
    assert 'aria-controls="' in exported_html
    assert 'aria-labelledby="' in exported_html


def test_iteration_tabs_are_prompt_evals_held_out(exported_html: str) -> None:
    for label in ("Prompt", "Evals", "Held-out"):
        assert f">{label}</button>" in exported_html


def test_exploration_tabs_are_problem_approaches_eval(exported_html: str) -> None:
    for label in ("Problem", "Approaches", "Eval"):
        assert f">{label}</button>" in exported_html


def test_version_selector_and_diff_navigation_hooks_exist(exported_html: str) -> None:
    assert 'id="version-select"' in exported_html
    assert 'data-action="diff-prev"' in exported_html
    assert 'data-action="diff-next"' in exported_html
    assert 'role="dialog"' in exported_html
    assert 'aria-modal="true"' in exported_html


def test_trial_navigation_hooks_exist(exported_html: str) -> None:
    assert 'data-action="trial-prev"' in exported_html
    assert 'data-action="trial-next"' in exported_html
    assert 'data-action="back-to-list"' in exported_html


def test_matrix_cells_are_real_buttons_with_version_case_labels(exported_html: str) -> None:
    assert 'data-matrix="eval"' in exported_html
    assert 'data-matrix="held-out"' in exported_html
    assert 'data-cell="' in exported_html
    assert "<button" in exported_html
    assert 'aria-label="' in exported_html


def test_trial_dialog_declares_four_panels(exported_html: str) -> None:
    dialog = re.search(
        r'<div[^>]*id="trial-dialog"[^>]*role="dialog"[^>]*>|"trial-dialog"', exported_html
    )
    assert dialog is not None
    for panel in ("answer", "evidence", "trace", "verifier"):
        assert f'data-panel="{panel}"' in exported_html


def test_trace_timeline_declares_four_lanes_in_recorded_lane_order(exported_html: str) -> None:
    for lane in ("input", "model", "tools", "verifier"):
        assert f'data-lane="{lane}"' in exported_html
    positions = [
        exported_html.index(f'data-lane="{lane}"')
        for lane in ("input", "model", "tools", "verifier")
    ]
    assert positions == sorted(positions)


def test_exploration_eval_table_has_recorded_metric_columns(exported_html: str) -> None:
    table_match = re.search(
        r'<table[^>]*id="eval-compare"[^>]*>(.*?)</table>', exported_html, re.DOTALL
    )
    assert table_match is not None
    table = table_match.group(1)
    for column in ("Passes", "Violations", "Tokens", "Latency"):
        assert column in table


def test_synthetic_badge_and_not_recorded_text_render(exported_html: str) -> None:
    assert "SYNTHETIC" in exported_html
    assert "synthetic-badge" in exported_html
    assert "未记录" in exported_html
    assert "not recorded" in exported_html


def test_embedded_data_preserves_distinct_tool_sequences_without_reordering(
    exported_html: str, studio_root: Path
) -> None:
    embedded = json.loads(DATA_SCRIPT_RE.findall(exported_html)[0])
    groups = embedded["iteration"]["eval_cases"]
    v0_trial = next(
        trial
        for group in groups
        if group["case_id"] == "case-01"
        for entry in group["entries"]
        if entry["version"] == "v0"
        for trial in entry["trials"]
        if trial["trial_id"] == "t1"
    )
    expected = read_trace(studio_root / "runs/v0/case-01/t1")
    assert [item["event_type"] for item in v0_trial["trace_panel"]["items"]] == [
        item.event_type for item in expected.items
    ]
    assert [
        item["payload"].get("name")
        for item in v0_trial["trace_panel"]["lanes"]["tools"]
        if item["event_type"] == "tool.call.completed"
    ] == ["transcribe_audio"]

    approaches = {a["id"]: a for a in embedded["exploration"]["approaches"]}
    full = approaches["full-approach"]
    recorded = []
    for trial, run in zip(full["trials"], ("runs/exp/full/t1", "runs/exp/full/t2")):
        direct = read_trace(studio_root / run)
        names = [
            item.payload["name"]
            for item in direct.items
            if item.event_type == "tool.call.completed"
        ]
        projected = [
            item["payload"]["name"]
            for item in trial["trace_panel"]["lanes"]["tools"]
            if item["event_type"] == "tool.call.completed"
        ]
        assert projected == names
        recorded.append(tuple(projected))
    assert recorded == [
        ("transcribe_audio", "sample_evidence"),
        ("sample_evidence", "transcribe_audio"),
    ]


def test_no_forbidden_rendering_primitives(exported_html: str) -> None:
    for forbidden in ("React", "react", "vite", "cdn.", "analytics", "telemetry"):
        assert forbidden not in exported_html


def test_trial_context_reset_is_a_single_function_wired_to_navigation(
    exported_html: str,
) -> None:
    assert exported_html.count("function resetTrialContext()") == 1

    select_tab = re.search(
        r"function selectTab\(tablist, tab\) \{(.*?)\n  \}", exported_html, re.DOTALL
    )
    assert select_tab is not None
    assert "resetTrialContext();" in select_tab.group(1)

    version_change = re.search(
        r'select\.addEventListener\("change", function \(\) \{(.*?)\}\);',
        exported_html,
        re.DOTALL,
    )
    assert version_change is not None
    assert "resetTrialContext();" in version_change.group(1)


def test_reset_trial_context_closes_without_restoring_focus_to_the_drawer(
    exported_html: str,
) -> None:
    body = re.search(r"function resetTrialContext\(\) \{(.*?)\n  \}", exported_html, re.DOTALL)
    assert body is not None
    reset_body = body.group(1)
    assert "closeOverlay" not in reset_body
    assert "trialWrap.hidden = true" in reset_body
    assert "focusStack.pop()" in reset_body
    assert "drawerState = null" in reset_body
    assert "dialogState = null" in reset_body


def test_navigation_buttons_have_explicit_dark_theme_styles(exported_html: str) -> None:
    for selector in (".trial-nav button", ".diff-nav button"):
        assert selector in exported_html
        rule = re.search(re.escape(selector) + r"[^{]*\{([^}]*)\}", exported_html)
        assert rule is not None
        for prop in ("background", "color", "border", "border-radius", "padding", "cursor"):
            assert prop in rule.group(1)
    assert ":focus-visible" in exported_html


def test_tool_trajectories_carry_visible_name_labels_in_recorded_order(
    exported_html: str,
) -> None:
    embedded = json.loads(DATA_SCRIPT_RE.findall(exported_html)[0])
    full = next(a for a in embedded["exploration"]["approaches"] if a["id"] == "full-approach")
    labels = []
    for trial in full["trials"]:
        names = [
            item["payload"]["name"]
            for item in trial["trace_panel"]["lanes"]["tools"]
            if item["event_type"] == "tool.call.completed"
        ]
        assert names and all(isinstance(name, str) and name for name in names)
        assert all(item["phase"] for item in trial["trace_panel"]["items"])
        labels.append(tuple(names))
    assert labels[0] == ("transcribe_audio", "sample_evidence")
    assert labels[1] == ("sample_evidence", "transcribe_audio")


def test_timeline_js_labels_tool_blocks_with_recorded_tool_names(exported_html: str) -> None:
    assert 'typeof item.payload.name === "string"' in exported_html
    assert "return item.payload.name" in exported_html


def test_event_detail_list_exposes_phase_and_full_projected_payload(exported_html: str) -> None:
    assert (
        '"#", "event", "lane", "phase", "payload", "status", "offset_ms", "duration_ms"'
        in exported_html
    )
    assert "JSON.stringify(item.payload)" in exported_html
    assert "payloadSummary" not in exported_html


def test_timeline_geometry_uses_completion_offset_semantics(exported_html: str) -> None:
    assert "Math.max(0, item.offset_ms - item.duration_ms)" in exported_html
    assert "panel.duration_ms" in exported_html


def test_verifier_recorded_empty_gates_render_none_not_missing(exported_html: str) -> None:
    assert 'verifier.provenance === "not_recorded"' in exported_html
    assert "verifier.failed_gates === null" in exported_html
    assert "none (0)" in exported_html


def test_null_verifier_aggregates_render_not_recorded(exported_html: str) -> None:
    assert "approach.metrics.passed_trials === null" in exported_html
    assert "approach.metrics.violations === null" in exported_html


def test_synthetic_note_does_not_deny_recorded_measurements(exported_html: str) -> None:
    assert "no recorded runs or measured values" not in exported_html
    assert "metrics appear only when the referenced RunBundle recorded them" in exported_html


def test_tool_name_labels_are_restricted_to_tool_call_events(exported_html: str) -> None:
    assert 'lane === "tools"' in exported_html
    assert 'item.event_type.indexOf("tool.call") === 0' in exported_html


def _overrun_trial_bundle(root: Path, relative_run: str) -> None:
    """A run whose verifier completes at 500 ms, after the 300 ms run duration."""
    bundle = RunBundle.create(
        root / relative_run,
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    recorder = TraceRecorder(bundle, clock=iter((0.0, 0.1, 0.2, 0.25, 0.3, 0.5)).__next__)
    run_span = recorder.start("run", phase="run")
    model_span = recorder.start("model.request", phase="agent_decision", turn=1, step=1)
    recorder.finish(model_span, status="completed")
    verifier_span = recorder.start("verifier", phase="verify_claims")
    recorder.finish(run_span, status="completed", phase="terminal")
    recorder.finish(
        verifier_span,
        status="completed",
        payload={"passed": True, "failed_gates": []},
    )
    bundle.finalize(TerminalState.SUCCEEDED)


def test_timeline_total_width_covers_events_completing_beyond_run_duration(tmp_path: Path) -> None:
    root = tmp_path / "overrun"
    _overrun_trial_bundle(root, "runs/v0/case-01/t1")
    manifest = {
        "api_version": "vidsnap.studio/v1",
        "iteration": {
            "agent_id": "overrun-agent",
            "versions": [
                {
                    "version": "v0",
                    "summary": "overrun probe",
                    "cases": [
                        {
                            "case_id": "case-01",
                            "trials": [{"trial_id": "t1", "run": "runs/v0/case-01/t1"}],
                        }
                    ],
                }
            ],
        },
    }
    manifest_path = root / "studio.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "overrun.html"

    export_studio(manifest_path, output)
    html = output.read_text(encoding="utf-8")

    embedded = json.loads(DATA_SCRIPT_RE.findall(html)[0])
    trial = embedded["iteration"]["eval_cases"][0]["entries"][0]["trials"][0]
    assert trial["trace"]["duration_ms"] == 300
    offsets = [
        item["offset_ms"] for item in trial["trace_panel"]["items"] if item["offset_ms"] is not None
    ]
    assert max(offsets) == 500
    assert max(offsets) > trial["trace"]["duration_ms"]
    assert "if (maxEnd > total) total = maxEnd;" in html
