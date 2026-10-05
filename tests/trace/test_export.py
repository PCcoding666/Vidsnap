"""RED tests for the self-contained, offline, redacted trace HTML export."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from vidsnap.trace import TraceDocument, read_trace
from vidsnap.trace.export import export_trace

# The exported page must carry its trace data in one inline JSON element so the
# viewer works offline; tests extract it to verify truth-only projection.
_DATA_SCRIPT = re.compile(
    r'<script id="vidsnap-trace-data" type="application/json">(.*?)</script>',
    re.DOTALL,
)
_MARKER = "__VIDSNAP_TRACE_JSON__"


def _embedded(html: str) -> Any:
    match = _DATA_SCRIPT.search(html)
    assert match is not None, "exported page must embed one vidsnap-trace-data script element"
    return json.loads(match.group(1))


def _documents(html: str) -> dict[str, dict[str, Any]]:
    data = _embedded(html)
    traces = data.get("traces") if isinstance(data, dict) and "traces" in data else {"run": data}
    assert isinstance(traces, dict) and traces
    return traces


def test_export_is_self_contained_and_contains_no_network_or_secrets(
    tmp_path: Path,
    traced_run: Path,
) -> None:
    output = export_trace(traced_run, tmp_path / "trace.html")

    assert output == tmp_path / "trace.html"
    html = output.read_text(encoding="utf-8")
    assert "tool.call.completed" in html
    for forbidden in ("https://", "fetch(", "WebSocket", "Authorization", "data:image"):
        assert forbidden not in html, f"offline export must not contain {forbidden!r}"
    for leaked in ("super-secret-key", "trace-provider.internal", "leaky-query", "must-not-appear"):
        assert leaked not in html


def test_export_embeds_the_exact_trace_document(tmp_path: Path, traced_run: Path) -> None:
    output = export_trace(traced_run, tmp_path / "trace.html")

    expected = read_trace(traced_run)
    html = output.read_text(encoding="utf-8")
    traces = _documents(html)
    document = TraceDocument.model_validate(next(iter(traces.values())))
    assert document == expected
    assert document.items and not document.summary_only


def test_single_json_projection_round_trips_and_is_script_safe(
    tmp_path: Path,
    escaping_run: Path,
) -> None:
    output = export_trace(escaping_run, tmp_path / "trace.html")
    html = output.read_text(encoding="utf-8")

    assert _MARKER not in html
    assert html.count('id="vidsnap-trace-data"') == 1
    # The duplicated plaintext projection is gone: exactly one embedded copy.
    assert "__VIDSNAP_TRACE_TEXT__" not in html

    serialized = json.dumps(
        read_trace(escaping_run).model_dump(mode="json"), ensure_ascii=True
    ).replace("<", "\\u003c")
    assert serialized in html
    document = TraceDocument.model_validate(next(iter(_documents(html).values())))
    assert document == read_trace(escaping_run)

    # Script-safe escaping: no breakout markup, payload quotes stay JSON-escaped.
    assert "</script><script>" not in html
    assert "\\u003cscript>" in html
    assert 'alert(\\"x\\")' in html
    assert 'alert("x")' not in html


def test_export_refuses_to_overwrite_non_empty_output(
    tmp_path: Path,
    traced_run: Path,
) -> None:
    output = tmp_path / "trace.html"
    output.write_text("existing content", encoding="utf-8")

    with pytest.raises(FileExistsError):
        export_trace(traced_run, output)
    assert output.read_text(encoding="utf-8") == "existing content"


def test_export_may_replace_an_existing_empty_output(
    tmp_path: Path,
    traced_run: Path,
) -> None:
    output = tmp_path / "trace.html"
    output.touch()

    assert export_trace(traced_run, output) == output
    assert output.read_text(encoding="utf-8")


def test_default_export_never_reads_evidence_artifacts(
    tmp_path: Path,
    run_with_evidence: Path,
) -> None:
    """Structured evidence JSON may be read; artifact bytes stay unread."""
    artifacts_dir = run_with_evidence / "artifacts"
    os.chmod(artifacts_dir, 0)
    try:
        output = export_trace(run_with_evidence, tmp_path / "trace.html")
    finally:
        os.chmod(artifacts_dir, 0o755)

    html = output.read_text(encoding="utf-8")
    assert "tool.call.completed" in html
    assert "PREVIEW_MARKER_7a2f" in html
    assert "ARTIFACT_BYTES_77e1" not in html


def test_legacy_export_is_visibly_summary_only(tmp_path: Path, legacy_smoke_dir: Path) -> None:
    output = export_trace(legacy_smoke_dir, tmp_path / "legacy.html")
    html = output.read_text(encoding="utf-8")

    assert "step-level events were not recorded" in html
    # Missing durations are rendered, never invented.
    assert "未记录" in html
    for invented in (
        "tool.call.completed",
        "tool.call.started",
        "model.request.completed",
        "run.completed",
        "probe.completed",
    ):
        assert invented not in html


def test_case_directory_export_embeds_all_variants_without_synthesizing_steps(
    tmp_path: Path,
    variant_case_dir: Path,
) -> None:
    output = export_trace(variant_case_dir, tmp_path / "case.html")
    html = output.read_text(encoding="utf-8")
    traces = _documents(html)

    assert set(traces) == {"direct", "fixed", "agentic"}
    sequences: dict[str, tuple[str, ...]] = {}
    for variant, raw in traces.items():
        expected = read_trace(variant_case_dir / variant / "run")
        document = TraceDocument.model_validate(raw)
        assert document == expected
        assert document.summary_only is False
        sequences[variant] = tuple(item.event_type for item in document.items)

    assert len(set(sequences.values())) == 3
    for variant in ("direct", "fixed", "agentic"):
        recorded = [
            item.event_type for item in read_trace(variant_case_dir / variant / "run").items
        ]
        assert list(sequences[variant]) == recorded


def _timeline_source() -> str:
    return files("vidsnap.trace").joinpath("assets/timeline.js").read_text(encoding="utf-8")


def test_exported_page_inlines_recorded_duration_and_timeline_math(
    tmp_path: Path,
    timed_run: Path,
) -> None:
    output = export_trace(timed_run, tmp_path / "trace.html")
    html = output.read_text(encoding="utf-8")

    document = next(iter(_documents(html).values()))
    assert document["duration_ms"] == 450
    # The page stays self-contained: the pure timeline math ships inlined once.
    assert _timeline_source() in html
    assert html.count("function timelineSpan(") == 1


def test_timeline_math_matches_recorded_spans_without_doubling(
    tmp_path: Path,
    timed_run: Path,
) -> None:
    """Execute the real exported timeline JS (Node is optional, never required).

    A completed event records offset_ms at completion plus duration_ms for the
    span, so a 450 ms run must render a 450 ms scale, never 900 ms.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; it is not a project dependency")

    document = read_trace(timed_run).model_dump(mode="json")
    assert document["duration_ms"] == 450
    doc_path = tmp_path / "doc.json"
    doc_path.write_text(json.dumps(document), encoding="utf-8")

    script = tmp_path / "timeline_check.js"
    script.write_text(
        _timeline_source()
        + """
const fs = require("fs");
const doc = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const spans = {};
for (const item of doc.items) spans[item.event_type] = itemSpan(item);
console.log(JSON.stringify({
  total: timelineSpan(doc),
  total_label: formatMs(timelineSpan(doc)),
  spans,
  zero_bytes: formatBytes(0),
  zero_ms_is_recorded: formatMs(0),
  missing: formatMs(null),
}));
""",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [node, str(script), str(doc_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(proc.stdout)

    assert result["total"] == 450
    assert result["total_label"] == "450 ms"
    assert result["spans"]["run.completed"] == [0, 450]
    assert result["spans"]["model.request.completed"] == [120, 200]
    assert result["spans"]["tool.call.completed"] == [310, 400]
    assert result["spans"]["run.started"] == [0, 0]
    assert result["spans"]["model.request.started"] == [120, 120]
    assert result["spans"]["tool.call.started"] == [310, 310]
    # Recorded-only metric semantics: zero is recorded, null is not.
    assert result["zero_bytes"] == "0 B"
    assert result["zero_ms_is_recorded"] == "0 ms"
    assert result["missing"] == "未记录"


def test_thumbnails_never_read_images_outside_the_run_bundle(
    tmp_path: Path,
    run_with_evidence: Path,
) -> None:
    outside_image = tmp_path / "outside.png"
    outside_image.write_bytes(b"OUTSIDE_SECRET_5b2e_png_bytes")
    (run_with_evidence / "artifacts" / "turn-1" / "escape.png").symlink_to(outside_image)
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "nested.png").write_bytes(b"OUTSIDE_DIR_SECRET_c4d1")
    (run_with_evidence / "artifacts" / "linkdir").symlink_to(outside_dir, target_is_directory=True)

    output = export_trace(run_with_evidence, tmp_path / "thumbs.html", include_thumbnails=True)
    html = output.read_text(encoding="utf-8")

    for raw in (b"OUTSIDE_SECRET_5b2e_png_bytes", b"OUTSIDE_DIR_SECRET_c4d1"):
        assert base64.b64encode(raw).decode("ascii") not in html
    inside = base64.b64encode(b"\xff\xd8ARTIFACT_BYTES_77e1").decode("ascii")
    assert f"data:image/jpeg;base64,{inside}" in html


def test_thumbnails_respect_extension_size_and_count_limits(
    tmp_path: Path,
    run_with_evidence: Path,
) -> None:
    artifacts = run_with_evidence / "artifacts" / "turn-1"
    for index in range(10):
        (artifacts / f"frame-{index:02d}.png").write_bytes(b"png" + bytes([index]) * 8)
    (artifacts / "notes.txt").write_text("not an image")
    oversized = b"x" * (256 * 1024 + 1)
    (artifacts / "too-big.png").write_bytes(oversized)

    output = export_trace(run_with_evidence, tmp_path / "thumbs.html", include_thumbnails=True)
    html = output.read_text(encoding="utf-8")

    assert html.count("data:image/") == 8
    assert "notes.txt" not in html
    assert base64.b64encode(oversized).decode("ascii")[:32] not in html


def test_thumbnail_collection_stops_at_the_bound_without_listing_a_ninth_file(
    tmp_path: Path,
    run_with_evidence: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts_root = run_with_evidence / "artifacts"
    frames = [artifacts_root / "turn-1" / f"frame-{index:02d}.png" for index in range(8)]
    for frame in frames:
        frame.write_bytes(b"\x89PNG" + frame.name.encode("ascii"))

    real_rglob = Path.rglob

    def guarded_rglob(self: Path, pattern: str) -> Any:
        if self != artifacts_root:
            return real_rglob(self, pattern)

        def yields() -> Any:
            yield from frames
            raise AssertionError(
                "thumbnail collection must stop at the bound; a ninth directory entry was requested"
            )

        return yields()

    monkeypatch.setattr(Path, "rglob", guarded_rglob)

    output = export_trace(run_with_evidence, tmp_path / "thumbs.html", include_thumbnails=True)
    html = output.read_text(encoding="utf-8")

    assert html.count("data:image/") == 8
    for frame in frames:
        assert base64.b64encode(frame.read_bytes()).decode("ascii") in html
