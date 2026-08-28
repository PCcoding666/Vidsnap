"""Documentation acceptance gates for the trust benchmark methodology."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_METHODOLOGY_DOC = "docs/benchmark-methodology.md"

_METRIC_NAMES = (
    "Temporal Grounding",
    "Citation Precision",
    "Unsupported Claim Rate",
    "Evidence Coverage",
    "Tool Budget Compliance",
    "Provider Regression",
    "Latency",
    "Cost",
    "Replay Determinism",
)

_FAIRNESS_FIELDS = (
    "source_sha256",
    "input_fingerprint",
    "transcript_condition",
    "transcript_fingerprint",
    "model",
    "dataset",
    "dataset_version",
    "available_evidence_fingerprint",
)

_INFRASTRUCTURE_SENTENCE = (
    "benchmark infrastructure ready; current results are not statistically meaningful."
)

_EVALUATE_COMMAND = "vidsnap benchmark evaluate INPUT_JSON --output REPORT_JSON"


def _read(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    lowered = [line.lower() for line in lines]
    start = next(
        index
        for index, line in enumerate(lines)
        if line.lstrip().startswith("#") and heading in lowered[index]
    )
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].lstrip().startswith("#")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_methodology_doc_exists_and_names_exactly_nine_trust_metrics() -> None:
    path = _REPO_ROOT / _METHODOLOGY_DOC
    assert path.is_file(), "docs/benchmark-methodology.md must exist"
    text = _read(_METHODOLOGY_DOC)
    for name in _METRIC_NAMES:
        assert name in text, f"methodology doc must name metric: {name}"


def test_methodology_doc_defines_deterministic_aggregation_and_unknown_not_zero() -> None:
    text = _read(_METHODOLOGY_DOC)
    lowered = text.lower()
    assert "numerator" in lowered and "denominator" in lowered
    assert "intersection-over-union" in lowered or "iou" in lowered
    assert "median" in lowered
    assert "unknown" in lowered
    assert "never zero" in lowered or "not zero" in lowered


def test_methodology_doc_defines_fair_direct_vs_harness_baseline() -> None:
    text = _read(_METHODOLOGY_DOC)
    lowered = text.lower()
    assert "direct" in lowered and "harness" in lowered
    for field in _FAIRNESS_FIELDS:
        assert field in text, f"methodology doc must document fairness field: {field}"
    assert "only declared evidence" in lowered
    assert "exactly one outcome" in lowered
    assert "cherry-picking" in lowered


def test_methodology_doc_documents_exact_offline_command_and_envelope() -> None:
    text = _read(_METHODOLOGY_DOC)
    assert _EVALUATE_COMMAND in text
    lowered = text.lower()
    assert "manifest" in lowered and "outcomes" in lowered
    assert "top-level" in lowered
    assert "manifest_sha256" in text
    assert "report_sha256" in text
    assert "sealed" in lowered


def test_methodology_doc_contains_exact_infrastructure_sentence() -> None:
    text = _read(_METHODOLOGY_DOC)
    assert _INFRASTRUCTURE_SENTENCE in text


def test_methodology_doc_publishes_no_result_claims() -> None:
    lowered = _read(_METHODOLOGY_DOC).lower()
    for statement in ("no live result", "no superiority", "no quality", "no latency", "no cost"):
        assert statement in lowered, f"methodology doc must state: {statement}"


def test_status_and_index_docs_link_the_methodology() -> None:
    assert "benchmark-methodology.md" in _read("docs/benchmark-status.md")
    assert "benchmark-methodology.md" in _read("docs/README.md")


def test_readme_benchmark_evidence_section_mentions_command_and_methodology() -> None:
    readme = _read("README.md")
    assert "benchmark evidence" in readme.lower()
    section = _section(readme, "benchmark evidence")
    assert "benchmark evaluate" in section.lower()
    assert "benchmark-methodology.md" in section
    assert _INFRASTRUCTURE_SENTENCE in section
