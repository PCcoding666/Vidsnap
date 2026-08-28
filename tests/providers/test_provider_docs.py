"""Docs contract for the provider extension axis (RED until docs exist).

Requires README.md and docs/README.md to link to docs/providers.md, and
requires docs/providers.md to state the provider boundary in plain text.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDERS_DOC = REPO_ROOT / "docs" / "providers.md"


def _normalized(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", text).lower()


def test_root_readme_links_to_providers_doc() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)\s]+\.md)[#)]", text)
    assert "docs/providers.md" in links, (
        "README.md must link to docs/providers.md under its docs links"
    )


def test_docs_readme_links_to_providers_doc() -> None:
    text = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)\s]+\.md)[#)]", text)
    assert "providers.md" in links, "docs/README.md must link to providers.md (relative to docs/)"


def test_providers_doc_exists() -> None:
    assert PROVIDERS_DOC.is_file(), "docs/providers.md must exist"


def test_providers_doc_states_application_fixes_provider_before_run() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "the application chooses one provider before a run" in body


def test_providers_doc_states_agent_cannot_switch_provider_or_model() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "the agent cannot choose or switch provider/model/base_url during a run" in body


def test_providers_doc_states_qwenprovider_is_reference() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "qwenprovider is the reference provider" in body


def test_providers_doc_states_mockprovider_is_deterministic_offline() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "mockprovider is deterministic offline" in body


def test_providers_doc_states_benchmarkprofile_locked_to_qwen3_8_max() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "benchmarkprofile remains locked to qwen3.8-max" in body


def test_providers_doc_states_provider_plugins_trusted_and_separate_axis() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "provider plugins are trusted code" in body
    assert "a separate extension axis from bounded tool plugins" in body


def test_providers_doc_states_explicit_allow_list_entry_points() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "provider entry points use an explicit allow-list" in body


def test_providers_doc_states_custom_provider_identities_must_not_contain_credentials() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "custom provider identities must not contain credentials" in body


def test_providers_doc_scopes_no_credentials_guarantee_to_builtin_providers() -> None:
    body = _normalized(PROVIDERS_DOC)
    assert "the no-credentials guarantee covers built-in providers only" in body
    assert "does not extend to third-party provider plugins" in body
    assert "credentials never appear in a bundle" not in body
