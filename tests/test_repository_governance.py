from pathlib import Path

ROOT = Path(__file__).parents[1]

ALLOWED_STATUSES = (
    "PROPOSED",
    "APPROVED",
    "IN_PROGRESS",
    "READY_FOR_REVIEW",
    "VERIFIED",
    "BLOCKED",
    "RELEASED",
)

REQUIRED_CONTRACT_FIELDS = (
    "Objective:",
    "Non-goals:",
    "Acceptance evidence:",
    "Authority / data / secret boundaries:",
    "Owner / executor / reviewer:",
    "Next human gate:",
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _task_contract_block(state: str, task_id: str) -> str:
    heading = f"## Task Contract: {task_id}"
    assert heading in state
    block = state.split(heading, 1)[1]
    next_heading = block.find("\n## ")
    if next_heading != -1:
        block = block[:next_heading]
    return block


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
    for field in REQUIRED_CONTRACT_FIELDS:
        assert field in state
    for status in ALLOWED_STATUSES:
        assert f"`{status}`" in state
    status_lines = [line for line in state.splitlines() if line.startswith("Status: `")]
    assert status_lines
    for line in status_lines:
        assert line.split("`")[1] in ALLOWED_STATUSES
    in_progress = [line for line in status_lines if line.split("`")[1] == "IN_PROGRESS"]
    assert len(in_progress) <= 1
    for pull_request in ("#7", "#8", "#9"):
        assert pull_request in state
    assert "Do not merge" in state


def test_project_state_tracks_stack_001_as_current_task_contract() -> None:
    state = _read("PROJECT_STATE.md")
    block = _task_contract_block(state, "STACK-001")

    for field in REQUIRED_CONTRACT_FIELDS:
        assert field in block
    assert "Status: `READY_FOR_REVIEW`" in block

    assert "#7" in state and "d4ac1e96" in state and "merged" in state
    assert "#8" in state and "887c25aa" in state
    assert "#9" in state and "04546ad9" in state
    pr_rows = [line for line in state.splitlines() if line.lstrip().startswith("| #")]
    for number, merge_commit in (("#7", "d4ac1e96"), ("#8", "887c25aa"), ("#9", "04546ad9")):
        rows = [line for line in pr_rows if line.lstrip().startswith(f"| {number} ")]
        assert rows, f"missing snapshot row for PR {number}"
        assert "MERGED" in rows[0].upper()
        assert merge_commit in rows[0]
    pr_10_rows = [line for line in pr_rows if line.lstrip().startswith("| #10 ")]
    assert pr_10_rows, "missing snapshot row for PR #10"
    pr_10_row = pr_10_rows[0].upper()
    assert "OPEN" in pr_10_row
    assert "READY" in pr_10_row
    assert "MERGED" not in pr_10_row
    assert "VIDSNAP_SLIM" in pr_10_row


def test_protocol_docs_record_batch_a_review_corrections() -> None:
    state = _read("PROJECT_STATE.md")

    assert "no live GitHub or provider query was performed" not in state
    assert "verified by the main agent on 2026-08-23" in state
    assert "read-only GitHub queries" in state
    assert "no GitHub state was modified" not in state
    assert "PRs #7, #8, and #9 were not modified" in state
    assert "GOV-001-authorized release actions" in state
    assert "https://github.com/PCcoding666/Vidsnap/pull/10" in state
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


def test_ci_runs_for_pull_requests_against_any_base() -> None:
    workflow = _read(".github/workflows/ci.yml")
    push = workflow.split("  push:", 1)[1].split("  pull_request:", 1)[0]
    pull_request = workflow.split("  pull_request:", 1)[1].split("\n\npermissions:", 1)[0]

    assert "vidsnap_slim" in push
    assert '"codex/**"' in push
    assert "branches:" not in pull_request


def test_ci_keeps_minimal_permissions_and_all_quality_gates() -> None:
    workflow = _read(".github/workflows/ci.yml")

    assert "permissions:\n  contents: read" in workflow
    for gate in (
        "ruff format --check src tests scripts",
        "ruff check .",
        "mypy src",
        "python -m pytest -q",
        "python -m build",
        "Wheel smoke test",
        "vidsnap conformance",
        "scripts/secret_scan.py",
        "git diff --check",
    ):
        assert gate in workflow


def test_security_policy_names_private_reporting_and_forbidden_artifacts() -> None:
    policy = _read("SECURITY.md").lower()
    for required in (
        "credential",
        "video",
        "dataset",
        "runbundle",
        "benchmark result",
        ".env",
        "cookie",
        "raw provider request",
        "raw provider response",
    ):
        assert required in policy
    assert "github" in policy
    assert "private" in policy
    assert "@" not in policy
    assert "never read" not in policy
    assert "local-first" in policy
    assert "never logged" in policy
    assert "private security contact" in policy
    assert "minimal public issue" in policy
    assert "vulnerability details" in policy


def test_dependabot_covers_python_and_github_actions_weekly() -> None:
    config = _read(".github/dependabot.yml")

    assert 'package-ecosystem: "pip"' in config
    assert 'package-ecosystem: "github-actions"' in config
    assert config.count('interval: "weekly"') == 2
