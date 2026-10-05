"""RED acceptance tests: static plugin project contract and validate-only API."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from vidsnap.contracts import default_loop_spec
from vidsnap.plugins.project import PluginProjectContract, validate_plugin_project

_OUTPUT_SCHEMA = {"$ref": "vidsnap://schemas/tool-result/v1"}

_VALID_CONTRACT = {
    "api_version": "vidsnap.plugin-project/v1",
    "id": "sample-tool",
    "name": "Sample Tool",
    "version": "0.1.0",
    "kind": "tool",
    "capabilities": {"provides": ["sample_tool"], "requires": ["transcribe_audio"]},
    "input_schema": {
        "type": "object",
        "properties": {"video_path": {"type": "string"}},
        "required": ["video_path"],
        "additionalProperties": False,
    },
    "output_schema": _OUTPUT_SCHEMA,
    "permissions": ["read_media_metadata"],
    "budget_impact": {
        "model_calls": 0,
        "provider_calls": 0,
        "tool_calls": 1,
        "evidence_frames": 0,
    },
    "entry_point": "sample-tool",
}

_ENTRY_POINT_TARGET = "sample_tool.plugin:TOOL"


def _write_project(
    root: Path,
    contract: dict | None = None,
    target: str = _ENTRY_POINT_TARGET,
    entry_key: str = "sample-tool",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(_VALID_CONTRACT if contract is None else contract)
    (root / "vidsnap.plugin.json").write_text(
        json.dumps(payload, ensure_ascii=True), encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "sample-tool"\n'
        'version = "0.1.0"\n'
        "\n"
        '[project.entry-points."vidsnap.plugins"]\n'
        f'{entry_key} = "{target}"\n',
        encoding="utf-8",
    )
    return root


def test_valid_project_returns_contract(tmp_path: Path) -> None:
    root = _write_project(tmp_path / "plugin")

    contract = validate_plugin_project(root)

    assert isinstance(contract, PluginProjectContract)
    assert contract.id == "sample-tool"
    assert contract.name == "Sample Tool"
    assert contract.version == "0.1.0"
    assert contract.kind == "tool"
    assert contract.output_schema == _OUTPUT_SCHEMA
    assert contract.entry_point == "sample-tool"


@pytest.mark.parametrize(
    "missing",
    ["vidsnap.plugin.json", "pyproject.toml"],
)
def test_missing_required_file_is_invalid(tmp_path: Path, missing: str) -> None:
    root = _write_project(tmp_path / "plugin")
    (root / missing).unlink()

    with pytest.raises(ValueError):
        validate_plugin_project(root)


def test_path_that_is_not_a_project_directory_is_invalid(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_plugin_project(tmp_path)
    plain_file = tmp_path / "plain.txt"
    plain_file.write_text("not a project", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_plugin_project(plain_file)


def test_unknown_and_extra_fields_are_rejected(tmp_path: Path) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["extra_field"] = 1
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / "extra", contract))


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "dupkeys"
    root.mkdir()
    (root / "vidsnap.plugin.json").write_text(
        json.dumps(_VALID_CONTRACT, ensure_ascii=True)[:-1] + ', "id": "other-tool"}',
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project.entry-points."vidsnap.plugins"]\nsample-tool = "sample_tool.plugin:TOOL"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        validate_plugin_project(root)


def test_duplicate_capability_names_are_rejected(tmp_path: Path) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["capabilities"] = {"provides": ["sample_tool", "sample_tool"], "requires": []}
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / "dupcap", contract))


def test_duplicate_permissions_are_rejected(tmp_path: Path) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["permissions"] = ["read_media_metadata", "read_media_metadata"]
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / "dupperm", contract))


@pytest.mark.parametrize(
    "permission",
    ["shell", "network", "secret", "pip_install", "write_shell"],
)
def test_unknown_permissions_are_rejected(tmp_path: Path, permission: str) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["permissions"] = [permission]
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / f"perm-{permission}", contract))


@pytest.mark.parametrize(
    "schema",
    ["not-an-object", ["list"], {"type": "array"}, {"type": "object"}, 42],
)
def test_malformed_input_schema_is_rejected(tmp_path: Path, schema) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["input_schema"] = schema
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / f"schema-{id(schema)}", contract))


_MISSING = object()


@pytest.mark.parametrize(
    ("additional_properties", "valid"),
    [
        (_MISSING, False),
        (True, False),
        (None, False),
        (0, False),
        ("false", False),
        (False, True),
    ],
    ids=["missing", "true", "null", "zero", "string-false", "boolean-false"],
)
def test_input_schema_additional_properties_must_be_boolean_false(
    tmp_path: Path,
    additional_properties: object,
    valid: bool,
) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    if additional_properties is _MISSING:
        contract["input_schema"].pop("additionalProperties", None)
    else:
        contract["input_schema"]["additionalProperties"] = additional_properties
    root = _write_project(tmp_path / "addprops", contract)

    if valid:
        assert isinstance(validate_plugin_project(root), PluginProjectContract)
    else:
        with pytest.raises(ValueError):
            validate_plugin_project(root)


@pytest.mark.parametrize(
    "required",
    [
        "video_path",
        ["video_path", "video_path"],
        ["does_not_exist"],
        ["video_path", 42],
    ],
    ids=["string-required", "duplicate-names", "unknown-name", "non-string-item"],
)
def test_input_schema_required_must_be_unique_strings_in_properties(
    tmp_path: Path,
    required: object,
) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["input_schema"]["required"] = required
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / "required", contract))


def test_output_schema_must_be_exact_tool_result_ref(tmp_path: Path) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["output_schema"] = {"$ref": "vidsnap://schemas/other/v1"}
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / "badref", contract))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_calls", -1),
        ("provider_calls", -1),
        ("tool_calls", -1),
        ("evidence_frames", -1),
    ],
)
def test_negative_budget_impact_is_rejected(tmp_path: Path, field: str, value: int) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["budget_impact"] = {**_VALID_CONTRACT["budget_impact"], field: value}
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / f"neg-{field}", contract))


@pytest.mark.parametrize(
    "field",
    ["model_calls", "provider_calls", "tool_calls", "evidence_frames"],
)
def test_budget_impact_above_default_loop_spec_caps_is_rejected(
    tmp_path: Path,
    field: str,
) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["budget_impact"] = {**_VALID_CONTRACT["budget_impact"], field: 1_000_000_000}
    spec = default_loop_spec()
    cap = getattr(spec, f"max_{field}", 1_000_000_000 - 1)
    assert 1_000_000_000 > cap
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / f"escalate-{field}", contract))


def test_entry_point_must_equal_plugin_id(tmp_path: Path) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["entry_point"] = "other-tool"
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / "mismatch", contract))


def test_pyproject_entry_point_key_must_match_plugin_id(tmp_path: Path) -> None:
    root = _write_project(tmp_path / "keymismatch", entry_key="other-tool")

    with pytest.raises(ValueError):
        validate_plugin_project(root)


@pytest.mark.parametrize(
    "target",
    ["os:system", "builtins:exec", "subprocess:run", "sample tool.plugin:TOOL", ""],
)
def test_unsafe_pyproject_import_target_is_rejected(tmp_path: Path, target: str) -> None:
    root = _write_project(tmp_path / f"unsafe-{abs(hash(target))}", target=target)

    with pytest.raises(ValueError):
        validate_plugin_project(root)


@pytest.mark.parametrize(
    "broken_line",
    [
        'name = = "sample-tool"',
        'name = "unclosed',
        "[project",
    ],
    ids=["double-equals", "unterminated-string", "unclosed-table-header"],
)
def test_broken_toml_syntax_is_rejected(tmp_path: Path, broken_line: str) -> None:
    root = _write_project(tmp_path / "broken-toml")
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            "[project]\n", f"[project]\n{broken_line}\n", 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        validate_plugin_project(root)


@pytest.mark.parametrize(
    "duplicate_key",
    ["sample-tool", "other-tool"],
    ids=["same-key", "other-key"],
)
def test_duplicate_entry_point_table_is_rejected(
    tmp_path: Path,
    duplicate_key: str,
) -> None:
    root = _write_project(tmp_path / "duplicate-table")
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8")
        + "\n"
        + '[project.entry-points."vidsnap.plugins"]\n'
        + f'{duplicate_key} = "{_ENTRY_POINT_TARGET}"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        validate_plugin_project(root)


def test_static_validation_never_executes_plugin_code(tmp_path: Path) -> None:
    root = _write_project(tmp_path / "plugin")
    package = root / "sample_tool"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "plugin.py").write_text(
        "import pathlib\n"
        "(pathlib.Path(__file__).resolve().parent.parent / 'sentinel.txt')"
        ".write_text('executed')\n"
        "TOOL = object()\n",
        encoding="utf-8",
    )

    contract = validate_plugin_project(root)

    assert contract.id == "sample-tool"
    assert not (root / "sentinel.txt").exists()


def test_version_must_be_semver(tmp_path: Path) -> None:
    contract = deepcopy(_VALID_CONTRACT)
    contract["version"] = "0.1"
    with pytest.raises(ValueError):
        validate_plugin_project(_write_project(tmp_path / "semver", contract))
