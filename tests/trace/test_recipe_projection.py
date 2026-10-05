"""RED test: the generic trace reader projects grounded claims from a recipe result."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from vidsnap.contracts import TerminalState, default_loop_spec
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.trace import read_trace

_RECIPE_RESULT = {
    "segments": [
        {
            "id": "seg-1",
            "kind": "answer",
            "speaker": "Guest",
            "start_time": 4.5,
            "end_time": 9.0,
            "source_text": "我觉得这个功能非常有用",
            "rendered_text": "I think this feature is very useful",
            "source_language": "zh",
            "rendered_language": "en",
            "transcript_evidence_id": "e02",
            "frame_evidence_id": "f01",
            "editorial_status": "faithful_translation",
        }
    ],
    "blocks": [
        {"id": "block-1", "type": "source", "segment_id": "seg-1"},
        {
            "id": "block-2",
            "type": "commentary",
            "text": "The answer highlights the usefulness of the feature.",
            "evidence_ids": ["e02", "f01"],
            "editorial_status": "model_commentary",
        },
    ],
    "brief_points": [
        {
            "id": "point-1",
            "commentary": "The interview confirms the feature is useful.",
            "evidence": ["e02", "f01"],
            "editorial_status": "model_commentary",
        }
    ],
}


def test_read_trace_projects_recipe_claims_in_deterministic_order(tmp_path: Path) -> None:
    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    bundle.finalize(TerminalState.SUCCEEDED)
    (bundle.path / "result.json").write_text(json.dumps(_RECIPE_RESULT), encoding="utf-8")

    trace = read_trace(bundle.path)

    projected = [(claim.text, claim.evidence_ids, claim.editorial_status) for claim in trace.claims]
    assert projected == [
        (
            "I think this feature is very useful",
            ["e02", "f01"],
            "faithful_translation",
        ),
        (
            "The answer highlights the usefulness of the feature.",
            ["e02", "f01"],
            "model_commentary",
        ),
        (
            "The interview confirms the feature is useful.",
            ["e02", "f01"],
            "model_commentary",
        ),
    ]
    assert not any("invalid" in limitation.lower() for limitation in trace.limitations)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda result: result.update(segments="not-a-list"),
            id="segments-not-a-list",
        ),
        pytest.param(
            lambda result: result["blocks"][1].update(evidence_ids=["e02", "e02"]),
            id="duplicate-commentary-evidence-ids",
        ),
        pytest.param(
            lambda result: result["segments"][0].update(rendered_text=""),
            id="empty-segment-rendered-text",
        ),
        pytest.param(
            lambda result: result["brief_points"][0].update(commentary=None),
            id="null-brief-commentary",
        ),
        pytest.param(
            lambda result: result["brief_points"].append({"id": "point-2"}),
            id="malformed-later-brief-point",
        ),
        pytest.param(
            lambda result: result["segments"][0].update(editorial_status="invented_status"),
            id="invented-segment-editorial-status",
        ),
        pytest.param(
            lambda result: result["blocks"][0].pop("segment_id"),
            id="source-block-missing-segment-id",
        ),
        pytest.param(
            lambda result: result["blocks"][1].update(editorial_status="source"),
            id="commentary-block-with-source-status",
        ),
        pytest.param(
            lambda result: result["blocks"][1].update(id="block-1"),
            id="duplicate-block-id-across-types",
        ),
        pytest.param(
            lambda result: result["brief_points"].append(dict(result["brief_points"][0])),
            id="duplicate-brief-point-id",
        ),
    ],
)
def test_read_trace_rejects_malformed_recipe_result(tmp_path: Path, mutate) -> None:
    result = deepcopy(_RECIPE_RESULT)
    mutate(result)

    bundle = RunBundle.create(
        tmp_path / "run",
        loop_spec=default_loop_spec(),
        provider_url="https://host/v1",
    )
    bundle.finalize(TerminalState.SUCCEEDED)
    (bundle.path / "result.json").write_text(json.dumps(result), encoding="utf-8")

    trace = read_trace(bundle.path)

    assert trace.claims == []
    assert any("invalid" in limitation.lower() for limitation in trace.limitations)
