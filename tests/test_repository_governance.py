from pathlib import Path

ROOT = Path(__file__).parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_project_state_defines_the_approved_task_contract() -> None:
    state = _read("PROJECT_STATE.md")

    for heading in (
        "# VidSnap Project State",
        "## Current Main Objective",
        "## Task Contract: GOV-001",
        "## Allowed States",
        "## Active Stacked Pull Requests",
        "## Repository Settings Requiring User Authorization",
    ):
        assert heading in state
    for field in (
        "Objective:",
        "Non-goals:",
        "Acceptance evidence:",
        "Authority / data / secret boundaries:",
        "Owner / executor / reviewer:",
        "Next human gate:",
    ):
        assert field in state
    for status in (
        "PROPOSED",
        "APPROVED",
        "IN_PROGRESS",
        "READY_FOR_REVIEW",
        "VERIFIED",
        "BLOCKED",
        "RELEASED",
    ):
        assert f"`{status}`" in state
    assert state.count("Status: `IN_PROGRESS`") == 1
    for pull_request in ("#7", "#8", "#9"):
        assert pull_request in state
    assert "Do not merge" in state


def test_protocol_docs_record_batch_a_review_corrections() -> None:
    state = _read("PROJECT_STATE.md")

    assert "no live GitHub or provider query was performed" not in state
    assert "verified by the main agent on 2026-08-23" in state
    assert "read-only GitHub queries" in state
    assert "no GitHub state was modified" in state
    assert "already closed" not in state

    contributing = _read("CONTRIBUTING.md")

    assert "maintainer-run agentic changes" in contributing
    assert "human contributors may implement directly" in contributing
    assert "Task Contract" in contributing
    assert "user merge gate" in contributing


def test_task_issue_form_requires_every_contract_field() -> None:
    form = _read(".github/ISSUE_TEMPLATE/task.yml")
    field_ids = (
        "objective",
        "non_goals",
        "acceptance_evidence",
        "boundaries",
        "roles",
        "next_human_gate",
    )
    for index, field_id in enumerate(field_ids):
        block = form.split(f"id: {field_id}", 1)[1]
        if index + 1 < len(field_ids):
            block = block.split(f"id: {field_ids[index + 1]}", 1)[0]
        assert "required: true" in block
    assert 'labels: ["task-contract"]' not in form
    assert "blank_issues_enabled: false" in _read(".github/ISSUE_TEMPLATE/config.yml")


def test_pull_request_template_preserves_evidence_and_human_gates() -> None:
    template = _read(".github/PULL_REQUEST_TEMPLATE.md")
    for required in (
        "## Task Contract",
        "Task ID",
        "## Acceptance Evidence",
        "## Authority and Data Boundaries",
        "## Verification",
        "No live benchmark",
        "does not authorize merge",
    ):
        assert required in template
    for ci_gate in (
        "mypy src",
        "python -m build",
        "vidsnap conformance",
        "scripts/secret_scan.py",
        "git diff --check",
    ):
        assert ci_gate in template
    assert "unless explicitly authorized" in template
    assert "outside the repository" in template
    assert "not committed" in template
