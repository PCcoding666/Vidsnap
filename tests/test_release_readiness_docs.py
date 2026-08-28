"""Release readiness documentation checks."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_PATH = REPO_ROOT / "docs" / "release-checklist.md"
README_PATH = REPO_ROOT / "docs" / "README.md"


def _collapsed_lower(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _collapsed(text: str) -> str:
    return " ".join(text.lower().split())


def test_checklist_exists_and_is_linked_from_docs_readme() -> None:
    assert CHECKLIST_PATH.is_file(), "docs/release-checklist.md must exist"
    readme = _collapsed_lower(README_PATH)
    assert "release-checklist.md" in readme


def test_checklist_contains_reusable_steps_and_verified_evidence() -> None:
    checklist = _collapsed_lower(CHECKLIST_PATH)
    assert "reusable release steps" in checklist
    assert "current verified evidence" in checklist


def test_checklist_covers_all_release_verification_phrases() -> None:
    checklist = _collapsed_lower(CHECKLIST_PATH)
    phrases = [
        "clean build",
        "wheel installation",
        "package import",
        "vidsnap --help",
        "zero-key",
        "vidsnap demo",
        "trace export",
        "plugin validate",
        "plugin test",
        "offline recipe fixture",
        "conformance",
        "secret scan",
        "ruff format",
        "ruff check",
        "mypy",
        "pytest",
        "wheel inspection",
        "json schema",
        "all prompts",
        "demo fixture",
        "trace assets",
        "package data",
        "cli entrypoint",
        "readme install",
        "example commands",
    ]
    for phrase in phrases:
        assert _collapsed(phrase) in checklist, f"missing phrase: {phrase}"


def test_checklist_benchmark_claims_are_scoped() -> None:
    checklist = _collapsed_lower(CHECKLIST_PATH)
    assert (
        _collapsed(
            "benchmark infrastructure ready; current results are not statistically meaningful."
        )
        in checklist
    )
    assert _collapsed("no live benchmark results are claimed") in checklist


def test_root_readme_pairs_editable_install_with_source_checkout() -> None:
    readme = _collapsed_lower(REPO_ROOT / "README.md")
    assert "pip install -e" in readme
    assert "source checkout" in readme
