"""Static plugin project contract: strict, validate-only, zero execution.

The project contract (`vidsnap.plugin-project/v1`) describes one installable
tool plugin. Validation is fully static: it reads `vidsnap.plugin.json` and
the `vidsnap.plugins` entry-point group from `pyproject.toml` and never
imports or executes plugin code.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator
from typing_extensions import Self

from vidsnap.contracts import default_loop_spec
from vidsnap.contracts.models import StrictModel

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

PROJECT_FILE = "vidsnap.plugin.json"
_OUTPUT_SCHEMA = {"$ref": "vidsnap://schemas/tool-result/v1"}
_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_SAFE_TARGET_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)
_FORBIDDEN_IMPORT_ROOTS = frozenset({"os", "sys", "subprocess", "shutil", "builtins", "importlib"})

Permission = Literal[
    "read_media_metadata",
    "read_audio",
    "sample_video_frames",
    "write_evidence",
    "write_artifacts",
]


class PluginProjectError(ValueError):
    """Raised when a plugin project fails static contract validation."""


class PluginCapabilities(StrictModel):
    """Model-selectable names this plugin provides or depends on."""

    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _names_are_unique_and_safe(self) -> Self:
        for group in (self.provides, self.requires):
            seen: set[str] = set()
            for name in group:
                if not _SAFE_NAME_RE.match(name):
                    raise PluginProjectError("capability names must be safe identifiers")
                if name in seen:
                    raise PluginProjectError("capability names must be unique")
                seen.add(name)
        return self


class BudgetImpact(StrictModel):
    """Nonnegative worst-case budget deltas, capped by the default LoopSpec."""

    model_calls: int = Field(ge=0)
    provider_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    evidence_frames: int = Field(ge=0)

    @model_validator(mode="after")
    def _within_default_caps(self) -> Self:
        budgets = default_loop_spec().budgets
        cap_by_field = {
            "model_calls": budgets.max_model_calls,
            "provider_calls": budgets.max_model_calls,
            "tool_calls": budgets.max_tool_calls,
            "evidence_frames": budgets.max_evidence_frames,
        }
        for field_name, value in self.model_dump().items():
            if value > cap_by_field[field_name]:
                raise PluginProjectError("budget_impact exceeds default LoopSpec caps")
        return self


class PluginProjectContract(StrictModel):
    """The strict, closed project contract for one tool plugin."""

    api_version: Literal["vidsnap.plugin-project/v1"]
    id: str = Field(min_length=1, max_length=256, pattern=r"^[a-z][a-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=32, pattern=r"^\d+\.\d+\.\d+$")
    kind: Literal["tool"]
    capabilities: PluginCapabilities
    input_schema: dict[str, object]
    output_schema: dict[str, str]
    permissions: tuple[Permission, ...] = ()
    budget_impact: BudgetImpact
    entry_point: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _input_schema_is_object_schema(self) -> Self:
        if self.input_schema.get("type") != "object" or isinstance(
            self.input_schema.get("type"), bool
        ):
            raise PluginProjectError("input_schema must be a JSON object schema")
        properties = self.input_schema.get("properties")
        if not isinstance(properties, dict):
            raise PluginProjectError("input_schema must declare properties")
        if self.input_schema.get("additionalProperties") is not False:
            raise PluginProjectError("input_schema must set additionalProperties to exactly false")
        required = self.input_schema.get("required", [])
        if not isinstance(required, list):
            raise PluginProjectError("input_schema required must be a list of property names")
        seen: set[str] = set()
        for name in required:
            if not isinstance(name, str):
                raise PluginProjectError("input_schema required entries must be strings")
            if name in seen:
                raise PluginProjectError("input_schema required entries must be unique")
            if name not in properties:
                raise PluginProjectError("input_schema required entries must exist in properties")
            seen.add(name)
        return self

    @model_validator(mode="after")
    def _output_schema_is_exact_tool_result_ref(self) -> Self:
        if self.output_schema != _OUTPUT_SCHEMA:
            raise PluginProjectError("output_schema must reference the tool-result schema")
        return self

    @model_validator(mode="after")
    def _permissions_are_unique(self) -> Self:
        if len(set(self.permissions)) != len(self.permissions):
            raise PluginProjectError("permissions must be unique")
        return self

    @model_validator(mode="after")
    def _entry_point_matches_id(self) -> Self:
        if self.entry_point != self.id:
            raise PluginProjectError("entry_point must equal the plugin id")
        return self


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PluginProjectError("vidsnap.plugin.json contains duplicate keys")
        result[key] = value
    return result


def _read_entry_point(pyproject_bytes: bytes) -> tuple[str, str]:
    """Extract the single vidsnap.plugins entry point with a strict TOML parser."""
    try:
        document = tomllib.loads(pyproject_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PluginProjectError("pyproject.toml is not valid TOML") from error
    project_table = document.get("project")
    if not isinstance(project_table, dict):
        raise PluginProjectError("pyproject.toml is missing the vidsnap.plugins entry-point group")
    entry_points_table = project_table.get("entry-points")
    if not isinstance(entry_points_table, dict):
        raise PluginProjectError("pyproject.toml is missing the vidsnap.plugins entry-point group")
    entry_point_group = entry_points_table.get("vidsnap.plugins")
    if not isinstance(entry_point_group, dict):
        raise PluginProjectError("pyproject.toml is missing the vidsnap.plugins entry-point group")
    if len(entry_point_group) != 1:
        raise PluginProjectError(
            "vidsnap.plugins entry-point group must declare exactly one plugin"
        )
    entry_key, target = next(iter(entry_point_group.items()))
    if not isinstance(entry_key, str) or not isinstance(target, str):
        raise PluginProjectError("pyproject entry point must map a string key to a string target")
    return entry_key, target


def validate_plugin_project(path: Path) -> PluginProjectContract:
    """Statically validate one plugin project directory without executing code."""
    if not path.is_dir():
        raise PluginProjectError("plugin project path must be an existing directory")
    contract_file = path / PROJECT_FILE
    pyproject_file = path / "pyproject.toml"
    if not contract_file.is_file() or not pyproject_file.is_file():
        raise PluginProjectError("plugin project requires vidsnap.plugin.json and pyproject.toml")
    try:
        raw = contract_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PluginProjectError("vidsnap.plugin.json is unreadable") from error
    try:
        data = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise PluginProjectError("vidsnap.plugin.json is not valid JSON") from error
    if not isinstance(data, dict):
        raise PluginProjectError("vidsnap.plugin.json must contain a JSON object")
    try:
        pyproject_bytes = pyproject_file.read_bytes()
    except OSError as error:
        raise PluginProjectError("pyproject.toml is unreadable") from error
    entry_key, target = _read_entry_point(pyproject_bytes)
    try:
        contract = PluginProjectContract.model_validate(data)
    except ValidationError as error:
        raise PluginProjectError(
            "vidsnap.plugin.json violates the plugin project contract"
        ) from error
    if entry_key != contract.id:
        raise PluginProjectError("pyproject entry-point key must match the plugin id")
    import_root = target.split(":", 1)[0].split(".", 1)[0]
    if not _SAFE_TARGET_RE.match(target) or import_root in _FORBIDDEN_IMPORT_ROOTS:
        raise PluginProjectError("pyproject entry-point target is not a safe import path")
    return contract
