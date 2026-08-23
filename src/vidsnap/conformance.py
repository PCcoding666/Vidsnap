"""Offline conformance checks for a releasable VidSnap Harness package."""

from __future__ import annotations

import json
import tempfile
from importlib.resources import files
from pathlib import Path

from pydantic import Field, JsonValue

from vidsnap.contracts import HarnessPolicy, default_loop_spec
from vidsnap.contracts.models import StrictModel, TerminalState
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.state_machine import BudgetExceeded, LoopController
from vidsnap.plugins.builtin import default_tool_plugins
from vidsnap.prompts import load_prompt_assets
from vidsnap.runtime.policies import default_plugin_registry

_FORBIDDEN_RUNTIME_TOKENS = (
    "sqlalchemy",
    "fastapi_users",
    "celery",
    "redis",
    "oauth",
    "smtp",
    "jwt",
)

_EXPECTED_TOOL_NAMES = ["sample_evidence", "transcribe_audio"]
_EXPECTED_FIXED_TOOL_ORDER = ["transcribe_audio", "sample_evidence"]
_EXPECTED_TRACE_SCHEMA = "vidsnap.trace/v1"
_EXPECTED_BUDGETS = {
    "max_model_calls": 12,
    "max_tool_calls": 6,
    "max_evidence_frames": 96,
    "max_wall_seconds": 900,
}


class ConformanceReport(StrictModel):
    """Named offline gate outcomes suitable for CLI and CI serialization."""

    passed: bool
    checks: dict[str, str | bool] = Field(default_factory=dict)
    details: dict[str, JsonValue] = Field(default_factory=dict)


def run_conformance() -> ConformanceReport:
    """Run no-network package checks and return every individual result."""
    checks: dict[str, str | bool] = {
        "loop_spec": _check_loop_spec(),
        "prompt_metadata": _check_prompt_metadata(),
        "output_schema": _check_output_schema(),
        "state_machine": _check_state_machine(),
        "forbidden_dependencies": _check_forbidden_dependencies(),
    }
    details: dict[str, JsonValue] = {}

    tool_names = _model_visible_tool_names()
    details["default_model_visible_tool_names"] = tool_names
    checks["default_model_visible_tools"] = tool_names == _EXPECTED_TOOL_NAMES

    fixed_order: list[JsonValue] = [plugin.name for plugin in default_tool_plugins()]
    details["fixed_default_tool_order"] = fixed_order
    checks["fixed_default_tool_order"] = fixed_order == _EXPECTED_FIXED_TOOL_ORDER

    checks["plugin_dependency_graph"] = _check_plugin_dependency_graph()
    checks["trace_template_packaged"] = _check_trace_template_packaged()

    trace_schema = _written_trace_schema()
    details["trace_schema"] = trace_schema
    checks["trace_schema"] = trace_schema == _EXPECTED_TRACE_SCHEMA

    checks["fixed_default_policy"] = HarnessPolicy().tool_mode == "fixed"

    budgets = default_loop_spec().budgets
    details["budgets"] = {
        "max_model_calls": budgets.max_model_calls,
        "max_tool_calls": budgets.max_tool_calls,
        "max_evidence_frames": budgets.max_evidence_frames,
        "max_wall_seconds": budgets.max_wall_seconds,
    }
    checks["budgets"] = details["budgets"] == _EXPECTED_BUDGETS

    return ConformanceReport(
        passed=all(_ok(status) for status in checks.values()),
        checks=checks,
        details=details,
    )


def _ok(status: str | bool) -> bool:
    """Treat both legacy string statuses and new boolean checks uniformly."""
    return status is True or status == "passed"


def _model_visible_tool_names() -> list[JsonValue]:
    try:
        registry = default_plugin_registry()
    except Exception:
        return []
    names = sorted(str(schema["name"]) for schema in registry.tool_schemas())
    return [name for name in names]


def _check_plugin_dependency_graph() -> bool:
    """Fail closed when the default plugin graph cannot be resolved."""
    try:
        default_plugin_registry().resolve()
    except Exception:
        return False
    return True


def _check_trace_template_packaged() -> bool:
    assets = files("vidsnap.trace").joinpath("assets")
    for name in ("trace.html", "timeline.js"):
        resource = assets.joinpath(name)
        if not resource.is_file() or not resource.read_text(encoding="utf-8").strip():
            return False
    return True


def _written_trace_schema() -> str | None:
    """Create one throwaway RunBundle and read the schema it actually declares."""
    try:
        with tempfile.TemporaryDirectory() as scratch:
            bundle = RunBundle.create(
                Path(scratch) / "probe",
                loop_spec=default_loop_spec(),
                provider_url="http://127.0.0.1:0",
            )
            manifest = json.loads((bundle.path / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    schema = manifest.get("trace_schema")
    return schema if isinstance(schema, str) else None


def _check_loop_spec() -> str:
    spec = default_loop_spec()
    if spec.api_version != "vidsnap.loop/v1" or len(spec.digest()) != 64:
        return "failed"
    return "passed"


def _check_prompt_metadata() -> str:
    spec_digest = default_loop_spec().digest()
    assets = load_prompt_assets()
    expected = {"planner", "evidence", "synthesizer", "verifier", "repair"}
    if set(assets) != expected:
        return "failed"
    if any(
        asset.loop_spec_sha256 != spec_digest or asset.model_config.get("model") != "qwen3.8-max"
        for asset in assets.values()
    ):
        return "failed"
    return "passed"


def _check_output_schema() -> str:
    schema = json.loads(
        files("vidsnap.contracts.schemas").joinpath("video_analysis.v1.json").read_text()
    )
    if schema.get("$id") != "vidsnap.video-analysis/v1":
        return "failed"
    return "passed" if schema.get("additionalProperties") is False else "failed"


def _check_state_machine() -> str:
    controller = LoopController(HarnessPolicy(max_model_calls=0))
    try:
        controller.record_model_call()
    except BudgetExceeded:
        return "passed" if controller.terminal_state is TerminalState.EXHAUSTED else "failed"
    return "failed"


def _check_forbidden_dependencies() -> str:
    repository_root = Path(__file__).resolve().parents[2]
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (repository_root / "src").rglob("*.py")
        if path.name != "conformance.py"
    ).lower()
    return "failed" if any(token in source for token in _FORBIDDEN_RUNTIME_TOKENS) else "passed"
