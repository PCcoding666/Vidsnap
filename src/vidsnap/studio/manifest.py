"""Strict pre-registered studio manifests with safe, contained run references.

The studio manifest is operator-authored JSON describing iteration and/or
exploration workspaces before or after runs happen. Validation is strict
(``extra="forbid"``), offline, and read-only; failure messages are category
descriptions only and never echo manifest values that may carry secrets.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from vidsnap.contracts.models import StrictModel

_SHA256_PATTERN = r"^[0-9a-fA-F]{64}$"
_URL_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_SECRET_MARKERS = (
    "api_key",
    "apikey",
    "api-key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "bearer ",
)
_LONG_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
_BEARER_PATTERN = re.compile(r"\bbearer\s+\S", re.IGNORECASE)
_ASSIGNMENT_PATTERN = re.compile(
    r"\b(api_key|apikey|api-key|authorization|cookie|password|secret|token)"
    r"\s*[=:]\s*\S",
    re.IGNORECASE,
)

ToolName = Annotated[str, Field(min_length=1, max_length=256)]


class StudioTrial(StrictModel):
    """One recorded attempt, referenced by a manifest-root-relative run path."""

    trial_id: str = Field(min_length=1, max_length=256)
    run: str = Field(min_length=1, max_length=4_096)

    @field_validator("run")
    @classmethod
    def _safe_relative_posix_reference(cls, value: str) -> str:
        _check_safe_run_reference(value)
        return value


def _check_safe_run_reference(reference: str) -> None:
    if "\x00" in reference or "\\" in reference:
        raise ValueError("run reference must not contain NUL bytes or backslashes")
    if "?" in reference or "#" in reference:
        raise ValueError("run reference must not contain query or fragment parts")
    if reference.startswith("/"):
        raise ValueError("run reference must be relative to the manifest root")
    if _URL_SCHEME_PATTERN.match(reference) is not None:
        raise ValueError("run reference must not use a URL scheme")
    parts = reference.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("run reference must be a clean relative POSIX path")


class IterationCase(StrictModel):
    """One evaluation case inside a prompt version, with its recorded trials."""

    case_id: str = Field(min_length=1, max_length=256)
    held_out: bool = False
    video_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    trials: list[StudioTrial] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_trials(self) -> IterationCase:
        seen: set[str] = set()
        for trial in self.trials:
            if trial.trial_id in seen:
                raise ValueError("trial_id must be unique within its case")
            seen.add(trial.trial_id)
        return self


class IterationVersion(StrictModel):
    """One prompt version with its change summary and registered cases."""

    version: str = Field(min_length=1, max_length=64, pattern=r"^v[0-9]+$")
    summary: str = Field(min_length=1, max_length=10_000)
    prompt: str | None = Field(default=None, max_length=100_000)
    prompt_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    cases: list[IterationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_cases(self) -> IterationVersion:
        seen: set[str] = set()
        for case in self.cases:
            if case.case_id in seen:
                raise ValueError("case_id must be unique within its version")
            seen.add(case.case_id)
        return self


class StudioIteration(StrictModel):
    """The existing-agent iteration workspace: prompt versions over cases."""

    agent_id: str = Field(min_length=1, max_length=256)
    versions: list[IterationVersion] = Field(min_length=1)

    @model_validator(mode="after")
    def _contiguous_versions(self) -> StudioIteration:
        for index, version in enumerate(self.versions):
            if version.version != f"v{index}":
                raise ValueError(
                    "iteration versions must be contiguous from v0 through vN"
                    " without gaps or duplicates"
                )
        return self


class StudioProblem(StrictModel):
    """The exploration target: a goal plus its declared constraints."""

    statement: str = Field(min_length=1, max_length=10_000)
    constraints: tuple[str, ...] = ()


class ApproachHarness(StrictModel):
    """The bounded harness configuration an approach ran under."""

    max_model_calls: int = Field(strict=True, ge=0, le=12)
    max_tool_calls: int = Field(strict=True, ge=0, le=6)
    tools: tuple[ToolName, ...] = ()

    @field_validator("tools")
    @classmethod
    def _unique_tools(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("harness tools must not contain duplicates")
        return value


class StudioApproach(StrictModel):
    """One candidate approach explored against the problem under budgets."""

    id: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=256)
    synthetic: bool = False
    prompt_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    harness: ApproachHarness
    trials: list[StudioTrial] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_trials(self) -> StudioApproach:
        seen: set[str] = set()
        for trial in self.trials:
            if trial.trial_id in seen:
                raise ValueError("trial_id must be unique within its approach")
            seen.add(trial.trial_id)
        return self


class StudioExploration(StrictModel):
    """The new-agent exploration workspace: one problem, several approaches."""

    problem: StudioProblem
    approaches: list[StudioApproach] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_approaches(self) -> StudioExploration:
        seen: set[str] = set()
        for approach in self.approaches:
            if approach.id in seen:
                raise ValueError("approach id must be unique within exploration")
            seen.add(approach.id)
        return self


class StudioEvalDefinition(StrictModel):
    """A pre-registered evaluation definition referenced by workspaces."""

    id: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=10_000)


class StudioManifest(StrictModel):
    """The operator pre-registered studio manifest (``vidsnap.studio/v1``)."""

    api_version: Literal["vidsnap.studio/v1"]
    title: str | None = Field(default=None, min_length=1, max_length=1_000)
    iteration: StudioIteration | None = None
    exploration: StudioExploration | None = None
    evals: list[StudioEvalDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _workspaces_and_eval_identity(self) -> StudioManifest:
        if self.iteration is None and self.exploration is None:
            raise ValueError("studio manifest requires at least one of iteration or exploration")
        seen: set[str] = set()
        for definition in self.evals:
            if definition.id in seen:
                raise ValueError("eval id must be unique within the manifest")
            seen.add(definition.id)
        return self


def load_studio_manifest(path: Path | str) -> StudioManifest:
    """Load, strictly validate, and containment-check a studio manifest."""
    manifest_path = Path(path)
    if not manifest_path.is_file() or not os.access(manifest_path, os.R_OK):
        raise ValueError("studio manifest must be a readable regular file")
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise ValueError("studio manifest is not readable UTF-8 text") from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("studio manifest is not valid JSON") from None
    if not isinstance(payload, dict):
        raise ValueError("studio manifest must be a JSON object")
    _reject_secret_shapes(payload)
    try:
        manifest = StudioManifest.model_validate(payload)
    except ValidationError:
        raise ValueError("studio manifest failed strict schema validation") from None
    _check_run_containment(manifest_path.parent.resolve(), manifest)
    return manifest


def _iter_run_references(manifest: StudioManifest) -> Iterator[str]:
    if manifest.iteration is not None:
        for version in manifest.iteration.versions:
            for case in version.cases:
                for trial in case.trials:
                    yield trial.run
    if manifest.exploration is not None:
        for approach in manifest.exploration.approaches:
            for trial in approach.trials:
                yield trial.run


def _check_run_containment(root: Path, manifest: StudioManifest) -> None:
    for reference in _iter_run_references(manifest):
        _check_safe_run_reference(reference)
        target = (root / reference).resolve()
        if not target.is_relative_to(root):
            raise ValueError("run reference escapes the manifest root")
        if not target.is_dir():
            raise ValueError("run reference points to a run bundle that does not exist")
        run_manifest = target / "manifest.json"
        try:
            resolved_manifest = run_manifest.resolve()
        except OSError:
            raise ValueError(
                "run reference points to an unresolvable run bundle manifest"
            ) from None
        if (
            not resolved_manifest.is_relative_to(root)
            or not resolved_manifest.is_file()
            or not os.access(resolved_manifest, os.R_OK)
        ):
            raise ValueError(
                "run reference points to a run bundle without a readable"
                " regular manifest.json inside the manifest root"
            )


def _reject_secret_shapes(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and _looks_like_secret_key(key):
                raise ValueError("studio manifest must not contain credential-bearing fields")
            _reject_secret_shapes(value)
    elif isinstance(payload, list):
        for item in payload:
            _reject_secret_shapes(item)
    elif isinstance(payload, str) and _looks_like_secret_value(payload):
        raise ValueError("studio manifest must not contain credential-bearing values")


def _looks_like_secret_key(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _SECRET_MARKERS)


def _looks_like_secret_value(text: str) -> bool:
    return (
        _BEARER_PATTERN.search(text) is not None
        or _ASSIGNMENT_PATTERN.search(text) is not None
        or _LONG_SECRET_PATTERN.search(text) is not None
    )
