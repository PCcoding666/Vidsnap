import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TAGLINE = "Build auditable video agents with bounded tools, plugins, and replayable traces."

TOPICS: tuple[str, ...] = (
    "video-ai",
    "agent-harness",
    "multimodal",
    "ai-agents",
    "video-analysis",
    "llm-evaluation",
    "python",
    "observability",
    "agent-runtime",
)


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def test_project_identity() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    first_nonempty_line = next(line for line in text.splitlines() if line.strip())
    assert first_nonempty_line == "# VidSnap"
    intro = text.split("\n##", 1)[0]
    assert TAGLINE in _normalize_whitespace(intro)


def test_readme_first_half_hero_and_guides() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    intro = text.split("\n##", 1)[0]
    first_half = text[: len(text) // 2]

    labels = [
        "Video",
        "Agent",
        "Tools",
        "Evidence",
        "Verified Output",
        "Replayable Trace",
    ]
    positions = [intro.find(label) for label in labels]
    assert all(position != -1 for position in positions)
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)

    intro_lower = intro.lower()
    for banned in ("benchmark", "qwen", "saas", "disclaimer"):
        assert banned not in intro_lower

    first_half_lower = first_half.lower()
    for phrase in (
        "What VidSnap does",
        "Why VidSnap exists",
        "not another video summarizer",
        "Quick Start",
        "What is a trace",
        "How to extend",
    ):
        assert phrase.lower() in first_half_lower

    assert "pip install" in first_half_lower
    assert "vidsnap --help" in first_half_lower or "vidsnap conformance" in first_half_lower
    assert "vidsnap trace export" in first_half_lower
    for concept in ("Core", "Plugin", "Recipe"):
        assert concept in first_half


def test_pyproject_description_and_topic_keywords() -> None:
    raw = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    description_match = re.search(r'^description\s*=\s*"([^"]*)"', raw, re.MULTILINE)
    assert description_match is not None
    assert description_match.group(1) == (
        "Auditable video-agent runtime with bounded tools, pluggable tasks, "
        "evidence-grounded outputs, and replayable traces."
    )

    keywords_match = re.search(r"^keywords\s*=\s*\[(.*?)\]", raw, re.MULTILINE | re.DOTALL)
    assert keywords_match is not None
    keywords = re.findall(r'"([^"]+)"', keywords_match.group(1))
    assert all(topic in keywords for topic in TOPICS)


def test_docs_landing_links_and_topics() -> None:
    raw = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert TAGLINE in _normalize_whitespace(raw)

    links = re.findall(r"\[([^\]]*)\]\(((?:\.\./)?README\.md#[^)]*)\)", raw)
    for anchor in (
        "quick-start",
        "trace",
        "plugin",
        "recipe",
        "benchmark",
        "contributing",
    ):
        assert any(
            anchor in link_text.lower() or anchor in link_href.lower()
            for link_text, link_href in links
        )

    docs_lower = raw.lower()
    assert all(topic in docs_lower for topic in TOPICS)


def test_readme_offers_thirty_second_zero_key_demo() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lowered = text.lower()

    assert "## 30-second demo" in lowered
    assert "vidsnap demo" in lowered
    assert "no zero-key demo" not in lowered
    assert lowered.index("## 30-second demo") < lowered.index("## quick start")
