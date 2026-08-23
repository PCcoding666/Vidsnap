"""Offline conformance checks for a releasable VidSnap Harness package."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from pydantic import Field

from vidsnap.contracts import HarnessPolicy, default_loop_spec
from vidsnap.contracts.models import StrictModel, TerminalState
from vidsnap.loop.state_machine import BudgetExceeded, LoopController
from vidsnap.prompts import load_prompt_assets

_FORBIDDEN_RUNTIME_TOKENS = (
    "sqlalchemy",
    "fastapi_users",
    "celery",
    "redis",
    "oauth",
    "smtp",
    "jwt",
)


class ConformanceReport(StrictModel):
    """Named offline gate outcomes suitable for CLI and CI serialization."""

    passed: bool
    checks: dict[str, str] = Field(default_factory=dict)


def run_conformance() -> ConformanceReport:
    """Run no-network package checks and return every individual result."""
    checks = {
        "loop_spec": _check_loop_spec(),
        "prompt_metadata": _check_prompt_metadata(),
        "output_schema": _check_output_schema(),
        "state_machine": _check_state_machine(),
        "forbidden_dependencies": _check_forbidden_dependencies(),
    }
    return ConformanceReport(
        passed=all(status == "passed" for status in checks.values()),
        checks=checks,
    )


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
