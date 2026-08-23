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
