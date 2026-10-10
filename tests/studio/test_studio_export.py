"""Single-file offline export: safety, escaping, overwrite rules, atomicity."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

import vidsnap.studio.export as export_module
from vidsnap.studio.export import export_studio
from vidsnap.studio.project import StudioDocument, project_studio

DATA_SCRIPT_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.DOTALL)


@pytest.fixture
def exported_html(studio_manifest_path: Path, tmp_path: Path) -> str:
    output = tmp_path / "export" / "eval-studio.html"
    export_studio(studio_manifest_path, output)
    return output.read_text(encoding="utf-8")


def test_export_is_a_single_offline_file(exported_html: str) -> None:
    for forbidden in (
        "https://",
        "http://",
        "fetch(",
        "WebSocket",
        "XMLHttpRequest",
        "src='",
        'src="',
        'href="',
        "<link",
        "@import",
    ):
        assert forbidden not in exported_html
    assert exported_html.count("<script") == 2
    assert exported_html.count("</script>") == 2


def test_inline_data_script_is_unique_and_equals_projection(
    exported_html: str, studio_manifest_path: Path
) -> None:
    matches = DATA_SCRIPT_RE.findall(exported_html)
    assert len(matches) == 1
    embedded = json.loads(matches[0])
    assert embedded == project_studio(studio_manifest_path).model_dump(mode="json")
    assert embedded["api_version"] == "vidsnap.studio.projection/v1"


def test_script_injection_payload_cannot_escape_the_data_script(
    studio_root: Path, tmp_path: Path, build_bundle
) -> None:
    build_bundle(
        studio_root,
        "runs/v2/case-01/t1",
        run_payload={"objective": 'answer </script><script>alert("x")</script>'},
    )
    manifest_path = studio_root / "studio.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["iteration"]["versions"].append(
        {
            "version": "v2",
            "summary": "injection probe",
            "cases": [
                {
                    "case_id": "case-01",
                    "trials": [{"trial_id": "t1", "run": "runs/v2/case-01/t1"}],
                }
            ],
        }
    )
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    output = tmp_path / "injection.html"
    export_studio(manifest_path, output)
    html = output.read_text(encoding="utf-8")

    assert html.count("<script") == 2
    assert "</script><script>" not in html
    assert "\\u003c" in html
    embedded = json.loads(DATA_SCRIPT_RE.findall(html)[0])
    document = StudioDocument.model_validate(embedded)
    assert document.api_version == "vidsnap.studio.projection/v1"


def test_refuses_to_overwrite_non_empty_output_and_preserves_it(
    studio_manifest_path: Path, tmp_path: Path
) -> None:
    output = tmp_path / "existing.html"
    original = "<html>existing operator content</html>"
    output.write_text(original, encoding="utf-8")

    with pytest.raises(FileExistsError):
        export_studio(studio_manifest_path, output)

    assert output.read_text(encoding="utf-8") == original


def test_existing_empty_output_is_refused(studio_manifest_path: Path, tmp_path: Path) -> None:
    output = tmp_path / "empty.html"
    output.touch()

    with pytest.raises(FileExistsError):
        export_studio(studio_manifest_path, output)

    assert output.stat().st_size == 0


def test_existing_directory_output_is_refused(studio_manifest_path: Path, tmp_path: Path) -> None:
    output = tmp_path / "a-directory"
    output.mkdir()

    with pytest.raises(FileExistsError):
        export_studio(studio_manifest_path, output)

    assert output.is_dir()


def test_existing_symlink_output_is_refused_and_target_preserved(
    studio_manifest_path: Path, tmp_path: Path
) -> None:
    target = tmp_path / "target.html"
    target.write_text("existing target content", encoding="utf-8")
    link = tmp_path / "link.html"
    os.symlink(target, link)

    with pytest.raises(FileExistsError):
        export_studio(studio_manifest_path, link)

    assert target.read_text(encoding="utf-8") == "existing target content"


def test_dangling_symlink_output_is_refused_and_left_intact(
    studio_manifest_path: Path, tmp_path: Path
) -> None:
    missing_target = tmp_path / "missing-target.html"
    link = tmp_path / "dangling.html"
    os.symlink(missing_target, link)

    with pytest.raises(FileExistsError):
        export_studio(studio_manifest_path, link)

    assert link.is_symlink()
    assert os.readlink(link) == str(missing_target)
    assert not missing_target.exists()
    leftovers = [path for path in tmp_path.iterdir() if path.name.startswith(".dangling.html.")]
    assert leftovers == []


def test_concurrent_creation_between_check_and_publish_is_never_clobbered(
    studio_manifest_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "raced.html"
    real_link = os.link

    def racing_link(src, dst, *args, **kwargs):
        Path(dst).write_text("competitor content", encoding="utf-8")
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(export_module.os, "link", racing_link)

    with pytest.raises(FileExistsError):
        export_studio(studio_manifest_path, output)

    assert output.read_text(encoding="utf-8") == "competitor content"
    leftovers = [path for path in tmp_path.iterdir() if path.name.startswith(".raced.html.")]
    assert leftovers == []


def test_dangling_reference_fails_before_any_output_is_written(tmp_path: Path) -> None:
    root = tmp_path / "dangling"
    root.mkdir()
    payload = {
        "api_version": "vidsnap.studio/v1",
        "iteration": {
            "agent_id": "video-summarizer",
            "versions": [
                {
                    "version": "v0",
                    "summary": "baseline",
                    "cases": [
                        {
                            "case_id": "case-01",
                            "trials": [{"trial_id": "t1", "run": "runs/missing/t1"}],
                        }
                    ],
                }
            ],
        },
    }
    manifest_path = root / "studio.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "never-written.html"

    with pytest.raises(ValueError):
        export_studio(manifest_path, output)

    assert not output.exists()
    leftovers = [path for path in tmp_path.iterdir() if path.name.startswith(".never-written.")]
    assert leftovers == []
