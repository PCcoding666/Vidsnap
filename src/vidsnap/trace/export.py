"""Self-contained, offline, redacted HTML exports of projected run traces."""

from __future__ import annotations

import base64
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from vidsnap.trace.reader import read_trace

_MARKER = "__VIDSNAP_TRACE_JSON__"
_TIMELINE_MARKER = "__VIDSNAP_TIMELINE_JS__"
_VARIANTS: tuple[str, ...] = ("direct", "fixed", "agentic")
_THUMBNAIL_MIME_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_MAX_THUMBNAILS = 8
_MAX_THUMBNAIL_BYTES = 256 * 1024


def export_trace(source: Path, output: Path, include_thumbnails: bool = False) -> Path:
    """Render one RunBundle, legacy result dir, or benchmark case to offline HTML.

    The default mode never opens evidence or artifact files; thumbnails are only
    embedded when explicitly requested and stay bounded to the source bundle.
    """
    source_path = source.resolve()
    output_path = output.resolve()
    if output_path.is_file() and output_path.stat().st_size > 0:
        raise FileExistsError(f"refusing to overwrite non-empty output: {output_path}")
    template = _load_template()
    if template.count(_MARKER) != 1 or template.count(_TIMELINE_MARKER) != 1:
        raise ValueError("packaged trace template must contain exactly one data marker")
    payload = _build_payload(source_path, include_thumbnails)
    serialized = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    html = template.replace(_MARKER, serialized)
    html = html.replace(_TIMELINE_MARKER, _load_timeline_script())
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _build_payload(source: Path, include_thumbnails: bool) -> dict[str, Any]:
    variant_runs = [
        (variant, source / variant / "run")
        for variant in _VARIANTS
        if (source / variant / "run").is_dir()
    ]
    if not variant_runs:
        document = read_trace(source).model_dump(mode="json")
        if not include_thumbnails:
            return document
        return {
            "traces": {"run": document},
            "thumbnails": {"run": _collect_thumbnails(source)},
        }
    traces = {
        variant: read_trace(run_path).model_dump(mode="json") for variant, run_path in variant_runs
    }
    payload: dict[str, Any] = {"traces": traces}
    if include_thumbnails:
        payload["thumbnails"] = {
            variant: _collect_thumbnails(run_path) for variant, run_path in variant_runs
        }
    return payload


def _collect_thumbnails(run_dir: Path) -> dict[str, str]:
    """Embed a bounded set of bundle-local images keyed by relative name only."""
    thumbnails: dict[str, str] = {}
    resolved_root = run_dir.resolve()
    for root_name in ("artifacts", "evidence"):
        root = run_dir / root_name
        if not root.is_dir():
            continue
        candidates = iter(root.rglob("*"))
        while True:
            # rglob is consumed lazily so the bound stops directory listing too.
            try:
                candidate = next(candidates)
            except StopIteration:
                break
            except OSError:
                break
            if not candidate.is_file():
                continue
            mime_type = _THUMBNAIL_MIME_TYPES.get(candidate.suffix.lower())
            if mime_type is None:
                continue
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            # Symlinks must never carry image bytes in from outside the bundle.
            if not resolved.is_relative_to(resolved_root):
                continue
            try:
                size = resolved.stat().st_size
                if size <= 0 or size > _MAX_THUMBNAIL_BYTES:
                    continue
                raw = resolved.read_bytes()
            except OSError:
                continue
            name = candidate.relative_to(run_dir).as_posix()
            thumbnails[name] = f"data:{mime_type};base64," + base64.b64encode(raw).decode("ascii")
            if len(thumbnails) >= _MAX_THUMBNAILS:
                return thumbnails
    return thumbnails


def _load_template() -> str:
    return files("vidsnap.trace").joinpath("assets/trace.html").read_text(encoding="utf-8")


def _load_timeline_script() -> str:
    return files("vidsnap.trace").joinpath("assets/timeline.js").read_text(encoding="utf-8")
