"""RED template tests: the examples/plugin-template project contract."""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

import pytest

from vidsnap.contracts.models import Evidence
from vidsnap.plugins.base import ToolExecutionContext, ToolPlugin, ToolResult
from vidsnap.plugins.project import validate_plugin_project
from vidsnap.video.probe import MediaProbe
from vidsnap.video.sampling import AdaptiveSampler

TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "examples" / "plugin-template"

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

PUBLIC_TEMPLATE_JSON_ASSETS = (
    "examples/plugin-template/vidsnap.plugin.json",
    "examples/plugin-template/example_run/probe.json",
    "examples/plugin-template/example_run/expected_result.json",
)

REQUIRED_FILES = (
    "pyproject.toml",
    "vidsnap.plugin.json",
    "src/video_metadata/__init__.py",
    "src/video_metadata/plugin.py",
    "tests/test_plugin.py",
    "README.md",
    "example_run/probe.json",
    "example_run/expected_result.json",
)

_FORBIDDEN_IMPORT_ROOTS = frozenset({"os", "subprocess", "socket", "requests", "httpx", "urllib"})
_FORBIDDEN_TEXT_TOKENS = ("sk-", "authorization")


class _RecordingEvidenceSink:
    def __init__(self) -> None:
        self.items: list[Evidence] = []

    def next_id(self, prefix: Literal["frame", "transcript"]) -> str:
        raise AssertionError("metadata template must not allocate evidence")

    def add(self, evidence: Evidence) -> str:
        self.items.append(evidence)
        raise AssertionError("metadata template must not store evidence")


class _RecordingMedia:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def __getattr__(self, name: str):
        def _record(*args: object, **kwargs: object) -> None:
            self.calls.append((name, args, kwargs))

        return _record


def _make_context(
    tmp_path: Path,
) -> tuple[ToolExecutionContext, _RecordingMedia, _RecordingEvidenceSink]:
    media = _RecordingMedia()
    sink = _RecordingEvidenceSink()
    context = ToolExecutionContext(
        source_path=tmp_path / "video.mp4",
        probe=MediaProbe(
            duration_seconds=10.0,
            fps=24,
            width=640,
            height=360,
            has_audio=True,
        ),
        artifact_root=tmp_path / "artifacts",
        media=media,
        recognizer=None,
        sampler=AdaptiveSampler(),
        evidence_sink=sink,
    )
    return context, media, sink


def _load_tool():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.syspath_prepend(str(TEMPLATE_ROOT / "src"))
    try:
        module = importlib.import_module("video_metadata.plugin")
    finally:
        monkeypatch.undo()
        sys.path = [entry for entry in sys.path if "plugin-template" not in entry]
    return module.TOOL


def test_template_contains_all_required_files() -> None:
    for relative in REQUIRED_FILES:
        assert (TEMPLATE_ROOT / relative).is_file(), f"missing template file: {relative}"


def test_public_template_json_assets_are_not_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--", *PUBLIC_TEMPLATE_JSON_ASSETS],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"git check-ignore rc={result.returncode} "
        f"(0 means a publishable template asset is ignored): {result.stdout}{result.stderr}"
    )


def test_validate_plugin_project_succeeds_with_single_video_metadata_entry() -> None:
    contract = validate_plugin_project(TEMPLATE_ROOT)

    assert contract.id == "video-metadata"
    assert contract.kind == "tool"
    pyproject_text = (TEMPLATE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert pyproject_text.count("video-metadata = ") == 1
    assert 'video-metadata = "video_metadata.plugin:TOOL"' in pyproject_text


def test_template_test_extra_covers_offline_pytest_requirements() -> None:
    pyproject = (TEMPLATE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    start = pyproject.find("[project.optional-dependencies]")
    assert start != -1, "template pyproject.toml must declare [project.optional-dependencies]"
    rest = pyproject[start + len("[project.optional-dependencies]") :]
    next_table = re.search(r"^\[", rest, re.MULTILINE)
    table = rest if next_table is None else rest[: next_table.start()]
    test_extra = re.search(r"^test\s*=\s*\[(.*?)\]", table, re.DOTALL | re.MULTILINE)
    assert test_extra is not None, "template pyproject.toml must expose a 'test' extra"
    names: set[str] = set()
    for spec in re.findall(r"[\"']([^\"']+)[\"']", test_extra.group(1)):
        matched = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", spec)
        if matched is not None:
            names.add(matched.group(0).lower())
    assert {"pytest", "pytest-asyncio"} <= names, (
        f"template 'test' extra must include pytest and pytest-asyncio, found {sorted(names)}"
    )

    readme = (TEMPLATE_ROOT / "README.md").read_text(encoding="utf-8")
    install = re.search(r"^python -m pip install[^\n]*\[test\]", readme, re.MULTILINE)
    assert install is not None, "template README install command must use the 'test' extra"
    pytest_command = readme.find("python -m pytest")
    assert pytest_command != -1, "template README must document the offline pytest command"
    assert install.start() < pytest_command, (
        "template README must install the 'test' extra before the offline pytest command"
    )


def test_example_run_files_are_valid_json_objects() -> None:
    for relative in ("example_run/probe.json", "example_run/expected_result.json"):
        payload = json.loads((TEMPLATE_ROOT / relative).read_text(encoding="utf-8"))
        assert isinstance(payload, dict), f"expected JSON object in {relative}"


def test_tool_factory_returns_runtime_plugin_matching_static_contract() -> None:
    contract = validate_plugin_project(TEMPLATE_ROOT)
    tool = _load_tool()

    plugin = tool()

    assert isinstance(plugin, ToolPlugin)
    assert plugin.manifest.id == contract.id
    assert plugin.manifest.version == contract.version
    assert plugin.manifest.kind == contract.kind
    assert tuple(plugin.manifest.provides) == contract.capabilities.provides
    assert tuple(plugin.manifest.requires) == contract.capabilities.requires


@pytest.mark.asyncio
async def test_execute_is_deterministic_metadata_result_without_side_effects(
    tmp_path: Path,
) -> None:
    validate_plugin_project(TEMPLATE_ROOT)
    plugin = _load_tool()()
    context, media, sink = _make_context(tmp_path)
    arguments = plugin.input_model()

    first = await plugin.execute(arguments, context)
    second = await plugin.execute(arguments, context)

    assert isinstance(first, ToolResult)
    assert first == second
    assert first.status == "completed"
    assert first.evidence_ids == ()
    assert first.usage.reported is False
    assert first.summary
    expected = json.loads(
        (TEMPLATE_ROOT / "example_run" / "expected_result.json").read_text(encoding="utf-8")
    )
    assert first.model_dump(mode="json") == expected
    assert media.calls == []
    assert sink.items == []
    assert not (tmp_path / "artifacts").exists()


def test_template_sources_pass_security_scan() -> None:
    scanned = 0
    for path in sorted(TEMPLATE_ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        scanned += 1
        lowered = text.lower()
        for token in _FORBIDDEN_TEXT_TOKENS:
            assert token not in lowered, f"forbidden token '{token}' in {path}"
        if path.suffix != ".py":
            continue
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            roots: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                roots = tuple(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                roots = (node.module.split(".", 1)[0],)
            for root in roots:
                assert root not in _FORBIDDEN_IMPORT_ROOTS, f"forbidden import '{root}' in {path}"
    assert scanned >= 4
