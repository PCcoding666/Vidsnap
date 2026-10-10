"""Self-contained, offline Eval Studio HTML exports.

``export_studio`` validates the manifest and projects every referenced
RunBundle *before* any output is written, then renders the frozen
``StudioDocument`` into a single HTML file with two inline scripts and no
remote references. Any existing output path (file, directory, or symlink) is
refused. The HTML is written to a same-directory temporary file, fsynced,
and published with an atomic no-replace hard link, so a concurrent writer can
never be clobbered.
"""

from __future__ import annotations

import os
import tempfile
from importlib.resources import files
from pathlib import Path

from vidsnap.studio.project import StudioDocument, project_studio

_DATA_MARKER = "__VIDSNAP_STUDIO_JSON__"
_SCRIPT_MARKER = "__VIDSNAP_STUDIO_JS__"


def export_studio(manifest_path: Path | str, output_path: Path | str) -> Path:
    """Project a studio manifest and publish one offline HTML workbench."""
    document = project_studio(manifest_path)
    # Never resolve the final component: a dangling symlink must be refused,
    # not followed into a target that would then be created.
    raw_output = Path(output_path).expanduser()
    if os.path.lexists(raw_output):
        raise FileExistsError("refusing to overwrite existing output")
    output = raw_output.parent.resolve() / raw_output.name
    html = _render(document)
    _atomic_publish(output, html)
    return output


def _render(document: StudioDocument) -> str:
    template = _load_asset("studio.html")
    if template.count(_DATA_MARKER) != 1 or template.count(_SCRIPT_MARKER) != 1:
        raise ValueError("packaged studio template must contain exactly one data marker")
    serialized = document.model_dump_json().replace("<", "\\u003c")
    html = template.replace(_DATA_MARKER, serialized)
    html = html.replace(_SCRIPT_MARKER, _load_asset("studio.js"))
    if html.count("<script") != 2 or _DATA_MARKER in html or _SCRIPT_MARKER in html:
        raise ValueError("studio export must embed exactly two inline scripts")
    return html


def _load_asset(name: str) -> str:
    return files("vidsnap.studio").joinpath(f"assets/{name}").read_text(encoding="utf-8")


def _atomic_publish(output: Path, html: str) -> None:
    """Write and fsync a temp file, then publish it with a no-replace link."""
    output.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
        text=True,
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(html)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, output)
        except FileExistsError:
            raise FileExistsError("refusing to overwrite existing output") from None
    finally:
        Path(temporary_path).unlink(missing_ok=True)
