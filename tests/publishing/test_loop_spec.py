"""RED-first tests: publish manifests must advertise the fixed 1/1/12 loop budgets.

The publishing runtime enforces HarnessPolicy with one tool call, one model
call, and twelve evidence frames, so the RunBundle manifest resources and the
loop-spec allow-list bound to that manifest must tell the same story. The
global default_loop_spec must remain untouched.
"""

from __future__ import annotations

import json

import pytest

from tests.publishing.test_service import run_service
from vidsnap.contracts import TerminalState, default_loop_spec
from vidsnap.publishing.service import publishing_loop_spec


@pytest.mark.asyncio
async def test_success_manifest_records_publishing_budgets_and_skills(tmp_path) -> None:
    result = await run_service(tmp_path)

    assert result.terminal_state is TerminalState.SUCCEEDED
    manifest = json.loads((result.run_path / "manifest.json").read_text(encoding="utf-8"))

    resources = manifest["resources"]
    assert resources["max_tool_calls"] == 1
    assert resources["max_model_calls"] == 1
    assert resources["max_evidence_frames"] == 12

    spec = publishing_loop_spec()
    assert spec.allowed_skills == (
        "probe_media",
        "sample_evidence",
        "synthesize_result",
        "verify_claims",
    )
    assert manifest["loop_spec"]["sha256"] == spec.digest()


def test_global_default_loop_spec_is_unchanged_by_publishing() -> None:
    defaults = default_loop_spec()

    assert defaults.budgets.max_tool_calls == 6
    assert defaults.budgets.max_model_calls == 12
    assert defaults.budgets.max_evidence_frames == 96
    assert defaults.allowed_skills == (
        "probe_media",
        "transcribe_audio",
        "sample_evidence",
        "inspect_evidence",
        "synthesize_result",
        "verify_claims",
    )
