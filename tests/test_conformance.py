"""Offline release-conformance behavior."""

from __future__ import annotations

from importlib.resources import files

from vidsnap.conformance import ConformanceReport, run_conformance
from vidsnap.contracts import HarnessPolicy
from vidsnap.plugins.builtin import default_tool_plugins
from vidsnap.runtime.policies import default_plugin_registry


def test_conformance_passes_for_default_package() -> None:
    report = run_conformance()

    assert report.passed is True
    assert report.checks["loop_spec"] == "passed"


def test_conformance_requires_exact_default_model_visible_tools_and_trace_asset() -> None:
    report = run_conformance()

    assert report.checks["default_model_visible_tools"] is True
    assert report.details["default_model_visible_tool_names"] == [
        "sample_evidence",
        "transcribe_audio",
    ]
    assert report.checks["trace_template_packaged"] is True
    assert report.checks["plugin_dependency_graph"] is True


def test_conformance_reports_trace_schema_fixed_policy_and_bounded_budgets() -> None:
    report = run_conformance()

    assert report.checks["trace_schema"] is True
    assert report.details["trace_schema"] == "vidsnap.trace/v1"
    assert report.checks["fixed_default_policy"] is True
    assert report.checks["budgets"] is True
    assert report.details["budgets"] == {
        "max_model_calls": 12,
        "max_tool_calls": 6,
        "max_evidence_frames": 96,
        "max_wall_seconds": 900,
    }


def test_conformance_pins_fixed_default_tool_order_in_report() -> None:
    """Order must be checked independently of the sorted model-visible set."""
    report = run_conformance()

    assert report.checks["fixed_default_tool_order"] is True
    assert report.details["fixed_default_tool_order"] == [
        "transcribe_audio",
        "sample_evidence",
    ]


def test_fixed_default_tool_order_is_transcribe_then_sample() -> None:
    """Independent of the canonical sorted set asserted above."""
    plugins = default_tool_plugins()

    assert [plugin.name for plugin in plugins] == ["transcribe_audio", "sample_evidence"]
    assert HarnessPolicy().tool_mode == "fixed"

    registry = default_plugin_registry()
    assert {plugin.name for plugin in registry.resolve()} == {
        "transcribe_audio",
        "sample_evidence",
    }


def test_default_plugin_registry_dependency_graph_resolves_with_exactly_two_tools() -> None:
    registry = default_plugin_registry()

    resolved = registry.resolve()
    assert {plugin.name for plugin in resolved} == {"transcribe_audio", "sample_evidence"}
    assert all(plugin.manifest.model_visible for plugin in resolved)
    names = [schema["name"] for schema in registry.tool_schemas()]
    assert sorted(names) == ["sample_evidence", "transcribe_audio"]


def test_trace_template_and_timeline_are_packaged_resources() -> None:
    template = files("vidsnap.trace").joinpath("assets/trace.html")
    timeline = files("vidsnap.trace").joinpath("assets/timeline.js")

    assert template.is_file()
    assert timeline.is_file()
    assert template.read_text(encoding="utf-8").strip()
    assert timeline.read_text(encoding="utf-8").strip()


def test_conformance_report_shape_allows_machine_readable_details() -> None:
    assert hasattr(ConformanceReport, "model_fields")
    assert "details" in ConformanceReport.model_fields
