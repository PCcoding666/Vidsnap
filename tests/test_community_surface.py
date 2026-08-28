"""Community surface contract tests (Phase 7)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PUBLIC_FILES = (
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "MAINTAINERS.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "ROADMAP.md",
    "docs/good-first-issues.md",
)

NON_GOALS = (
    "SaaS accounts",
    "hosted video library",
    "arbitrary shell agent",
    "unrestricted browser agent",
    "plugin marketplace",
    "social publishing platform",
)

ISSUE_FORM_NAMES = {
    "Bug",
    "Plugin proposal",
    "Recipe proposal",
    "Provider compatibility",
    "Documentation",
}

INTERNAL_TERMS = ("codex", "qoder", "project_state", "task contract", "task card")

CONTRIBUTING_FORBIDDEN = INTERNAL_TERMS + ("internal orchestration",)


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", PUBLIC_FILES)
def test_public_file_exists(name: str) -> None:
    assert (ROOT / name).is_file() and read(name).strip()


def test_contributing_is_public_and_actionable() -> None:
    text = read("CONTRIBUTING.md")
    lowered = text.lower()
    assert "pip install" in lowered
    assert "pytest" in lowered
    under_ten = r"(?:under|less than|<)\s*10\s*minutes"
    assert re.search(rf"(?i)full (?:test )?suite.{{0,60}}{under_ten}", text) or re.search(
        rf"(?i){under_ten}.{{0,60}}full (?:test )?suite", text
    ), "CONTRIBUTING.md lacks a full-suite under-10-minutes statement"
    for term in CONTRIBUTING_FORBIDDEN:
        assert term not in lowered, f"CONTRIBUTING.md mentions internal term: {term}"


def test_agents_md_covers_coding_agent_topics() -> None:
    lowered = read("AGENTS.md").lower()
    for topic in (
        "architecture",
        "scope",
        "tests",
        "security",
        "boundaries",
        "allowed",
        "forbidden",
    ):
        assert topic in lowered, f"AGENTS.md lacks topic: {topic}"


def test_maintainers_policy_topics() -> None:
    lowered = read("MAINTAINERS.md").lower()
    for topic in ("ai-assisted", "review", "release", "compat", "benchmark", "secret"):
        assert topic in lowered, f"MAINTAINERS.md lacks topic: {topic}"


def test_roadmap_headings_and_exact_non_goals() -> None:
    text = read("ROADMAP.md")
    for heading in ("Now", "Next", "Later", "Non-goals"):
        assert re.search(rf"^#+\s+{heading}\s*$", text, re.MULTILINE), f"missing heading: {heading}"
    match = re.search(r"^#+\s+Non-goals\s*$\n(.*?)(?=^#+\s|\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "Non-goals section not found"
    bullets = re.findall(r"^[-*]\s+(.+?)\s*$", match.group(1), re.MULTILINE)
    assert len(bullets) == len(NON_GOALS), (
        f"expected {len(NON_GOALS)} non-goal bullets, found {len(bullets)}"
    )
    lowered_bullets = [b.lower() for b in bullets]
    for goal in NON_GOALS:
        assert any(goal.lower() in b for b in lowered_bullets), f"missing non-goal: {goal}"


def test_security_topics_covered() -> None:
    lowered = read("SECURITY.md").lower()
    for topic in (
        "supported version",
        "private",
        "provider",
        "plugin",
        "credential",
        "runbundle",
        ".env",
    ):
        assert topic in lowered, f"SECURITY.md lacks topic: {topic}"


def test_exactly_five_issue_forms_and_no_task_yml() -> None:
    forms_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
    files = sorted(p for p in forms_dir.glob("*.yml") if p.name != "config.yml")
    names: set[str] = set()
    for path in files:
        match = re.search(r"^name:\s*(.+?)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
        assert match, f"form without name: {path.name}"
        names.add(match.group(1).strip())
    assert names == ISSUE_FORM_NAMES
    assert len(files) == len(ISSUE_FORM_NAMES)
    assert not any(p.name == "task.yml" for p in forms_dir.glob("*"))


def test_pull_request_template_sections() -> None:
    text = read(".github/PULL_REQUEST_TEMPLATE.md")
    for section in ("Summary", "Tests", "Security", "Compatibility"):
        assert re.search(rf"(?im)^#+\s*{section}\b", text), f"PR template lacks section: {section}"
    lowered = text.lower()
    for term in INTERNAL_TERMS:
        assert term not in lowered, f"PR template mentions internal term: {term}"


def test_five_to_ten_good_first_issue_entries() -> None:
    text = read("docs/good-first-issues.md")
    outcomes = len(re.findall(r"(?i)\boutcome\b", text))
    assert 5 <= outcomes <= 10, f"expected 5-10 entries, found {outcomes} Outcome labels"
    for label in ("files", "acceptance", "non-goals"):
        count = len(re.findall(rf"(?i)\b{re.escape(label)}\b", text))
        assert count >= outcomes, f"missing {label} labels: {count} < {outcomes}"


@pytest.mark.parametrize("readme", ["README.md", "docs/README.md"])
def test_readmes_link_current_surface(readme: str) -> None:
    text = read(readme)
    for target in ("CONTRIBUTING.md", "ROADMAP.md", "SECURITY.md"):
        assert re.search(rf"\]\([^)]*{re.escape(target)}[^)]*\)", text), (
            f"{readme} lacks link to {target}"
        )
    for topic in ("plugin", "recipe", "provider"):
        assert re.search(rf"\]\([^)]*{topic}", text, re.IGNORECASE), f"{readme} lacks {topic} link"
    assert not re.search(r"(?i)\bno (?:plugin sdk|recipes?)\b", text), (
        f"{readme} contains stale claim that plugin SDK or recipes are absent"
    )
    assert not re.search(
        r"(?i)(?:plugin sdk|recipes?)\b[^.\n]{0,60}"
        r"\b(?:is|are) not (?:yet )?(?:available|supported|included)",
        text,
    ), f"{readme} contains stale claim that plugin SDK or recipes are absent"
