"""Blind A/B human review: one offline page, a separate key, and an import step.

The page shows two systems' outputs for each item as A and B in a seeded random
order, with the task rubric. Scores are saved by the reviewer as a JSON file
(the page makes no network request); the A/B key is written to a separate file
the page never contains. ``import_scores`` un-blinds scores into
``vidsnap.eval-human/v1`` for ``vidsnap eval report``.
"""

from __future__ import annotations

import base64
import html
import json
import random
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vidsnap.eval.report import HUMAN_SCHEMA, HumanScore, HumanScores
from vidsnap.eval.rubrics import Rubric, get_rubric

SCORES_SCHEMA = "vidsnap.eval-review-scores/v1"
KEY_SCHEMA = "vidsnap.eval-review-key/v1"
_MAX_IMAGES = 12
_MAX_IMAGE_BYTES = 400_000
_IMAGE_LINE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)$")
_ORDERED = re.compile(r"^\d+\.\s+(?P<text>.*)$")


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)


def markdown_to_html(markdown: str, base_dir: Path) -> str:
    """A small converter for the renderer's own Markdown; all model text is escaped."""
    parts: list[str] = []
    images = 0
    list_kind: str | None = None

    def close_list() -> None:
        nonlocal list_kind
        if list_kind is not None:
            parts.append(f"</{list_kind}>")
            list_kind = None

    for raw in markdown.splitlines():
        line = raw.rstrip()
        image = _IMAGE_LINE.match(line)
        ordered = _ORDERED.match(line)
        if not line:
            close_list()
            continue
        if line.startswith("#"):
            close_list()
            level = min(4, len(line) - len(line.lstrip("#")) + 1)
            parts.append(f"<h{level}>{_inline(line.lstrip('#').strip())}</h{level}>")
        elif image is not None:
            close_list()
            path = (base_dir / image.group("path")).resolve()
            if (
                images < _MAX_IMAGES
                and path.is_relative_to(base_dir.resolve())
                and path.is_file()
                and path.stat().st_size <= _MAX_IMAGE_BYTES
            ):
                images += 1
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                parts.append(
                    f'<img alt="{html.escape(image.group("alt"))}" '
                    f'src="data:image/jpeg;base64,{encoded}">'
                )
            else:
                parts.append(f"<p class=muted>[图片未嵌入：{html.escape(image.group('alt'))}]</p>")
        elif line.startswith("- ") or ordered is not None:
            kind = "ul" if line.startswith("- ") else "ol"
            if list_kind != kind:
                close_list()
                parts.append(f"<{kind}>")
                list_kind = kind
            text = line[2:] if kind == "ul" else (ordered.group("text") if ordered else line)
            parts.append(f"<li>{_inline(text)}</li>")
        else:
            close_list()
            parts.append(f"<p>{_inline(line)}</p>")
    close_list()
    return "\n".join(parts)


def _output_html(record: dict[str, Any]) -> str:
    render_value = record.get("render")
    render: dict[str, Any] = render_value if isinstance(render_value, dict) else {}
    directory = Path(str(render.get("dir"))) if render.get("dir") else None
    if directory is None or not directory.is_dir():
        reason = record.get("failure_category") or record.get("terminal_state") or "no output"
        return f"<p class=muted>（没有产出：{html.escape(str(reason))}）</p>"
    blocks: list[str] = []
    for name in ("article.md", "review.md", "notes.md", "script.md"):
        path = directory / name
        if path.is_file():
            blocks.append(markdown_to_html(path.read_text(encoding="utf-8"), directory))
    video = directory / "video.html"
    if video.is_file():
        blocks.append(
            '<iframe sandbox="allow-scripts" title="video" srcdoc="'
            + html.escape(video.read_text(encoding="utf-8"), quote=True)
            + '"></iframe>'
        )
    return "\n".join(blocks) or "<p class=muted>（没有可展示的文件）</p>"


def _rubric_html(rubric: Rubric, pair_id: str) -> str:
    rows: list[str] = []
    for dimension in rubric.dimensions:
        cells = []
        for side in ("A", "B"):
            radios = "".join(
                f'<label><input type="radio" name="{pair_id}-{side}-{dimension.id}" '
                f'value="{score}">{score}</label>'
                for score in range(1, 6)
            )
            cells.append(f"<td>{side}: {radios}</td>")
        anchors = " ／ ".join(
            f"{score}={html.escape(text)}" for score, text in zip((1, 3, 5), dimension.anchors)
        )
        rows.append(
            f"<tr><th>{html.escape(dimension.name)}<div class=muted>"
            f"{html.escape(dimension.question)}<br>{anchors}</div></th>{''.join(cells)}</tr>"
        )
    preference = "".join(
        f'<label><input type="radio" name="{pair_id}-preference" value="{value}">{label}</label>'
        for value, label in (("A", "A 更好"), ("B", "B 更好"), ("tie", "差不多"))
    )
    minutes = "".join(
        f'<label>{side} 估计修改分钟：<input type="number" min="0" step="1" '
        f'name="{pair_id}-{side}-edit"></label>'
        for side in ("A", "B")
    )
    return (
        f"<table class=rubric>{''.join(rows)}</table>"
        f"<p>总体偏好：{preference}</p><p>{minutes}</p>"
        f'<p><textarea name="{pair_id}-note" placeholder="备注（可选）"></textarea></p>'
    )


_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root { --bg:#fbfaf7; --ink:#1d1d1f; --muted:#6b6b70; --line:#dedbd2; --card:#ffffff; }
@media (prefers-color-scheme: dark) { :root { --bg:#16171a; --ink:#ececec; --muted:#9a9aa2;
  --line:#2c2d33; --card:#1e1f24; } }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.6 "PingFang SC",sans-serif; }
main { max-width:1400px; margin:0 auto; padding:16px; }
.pair { border:1px solid var(--line); border-radius:8px; margin:24px 0; padding:12px;
  background:var(--card); }
.sides { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
@media (max-width:800px) { .sides { grid-template-columns:1fr; } }
.side { border:1px solid var(--line); border-radius:6px; padding:8px; max-height:70vh;
  overflow:auto; }
.side img { max-width:100%; } iframe { width:100%; aspect-ratio:16/10; border:0; }
.muted { color:var(--muted); font-size:13px; }
table.rubric { width:100%; border-collapse:collapse; }
table.rubric th, table.rubric td { border-top:1px solid var(--line); padding:6px; text-align:left;
  vertical-align:top; } label { margin-right:8px; white-space:nowrap; } textarea { width:100%; }
#bar { position:sticky; top:0; background:var(--bg); padding:8px 0;
  border-bottom:1px solid var(--line); }
</style></head><body><main>
<div id="bar"><strong>__TITLE__</strong> · 共 __COUNT__ 组 ·
<button id="save" type="button">导出评分 JSON</button>
<span class="muted">评分会自动暂存在本浏览器；完成后点“导出评分 JSON”，
把文件交给 vidsnap eval review import。</span></div>
<p class="muted">__HUMAN_ONLY__</p>
<form id="form">__PAIRS__</form>
</main>
<script type="application/json" id="meta">__META__</script>
<script>
(function () {
  "use strict";
  var meta = JSON.parse(document.getElementById("meta").textContent);
  var form = document.getElementById("form");
  var storeKey = "vidsnap-review-" + meta.review_id;
  function collect() {
    var data = new FormData(form);
    var pairs = meta.pairs.map(function (pairId) {
      var dims = { A: {}, B: {} };
      meta.dimensions.forEach(function (dim) {
        ["A", "B"].forEach(function (side) {
          var value = data.get(pairId + "-" + side + "-" + dim);
          if (value) { dims[side][dim] = parseInt(value, 10); }
        });
      });
      function minutes(side) {
        var value = data.get(pairId + "-" + side + "-edit");
        return value === null || value === "" ? null : parseFloat(value);
      }
      return { pair_id: pairId, dimensions: dims,
        preference: data.get(pairId + "-preference"),
        edit_minutes: { A: minutes("A"), B: minutes("B") },
        note: data.get(pairId + "-note") || null };
    });
    return { schema_version: meta.schema_version, review_id: meta.review_id,
      suite_id: meta.suite_id, saved_at: new Date().toISOString(), pairs: pairs };
  }
  function restore() {
    var saved = null;
    try {
      saved = JSON.parse(window.localStorage.getItem(storeKey) || "null");
    } catch (e) { saved = null; }
    if (!saved || !saved.pairs) { return; }
    saved.pairs.forEach(function (pair) {
      ["A", "B"].forEach(function (side) {
        Object.keys(pair.dimensions[side] || {}).forEach(function (dim) {
          var input = form.querySelector('input[name="' + pair.pair_id + "-" + side + "-" + dim +
            '"][value="' + pair.dimensions[side][dim] + '"]');
          if (input) { input.checked = true; }
        });
        var edit = form.querySelector('input[name="' + pair.pair_id + "-" + side + '-edit"]');
        if (edit && pair.edit_minutes && pair.edit_minutes[side] !== null) {
          edit.value = pair.edit_minutes[side];
        }
      });
      if (pair.preference) {
        var pref = form.querySelector('input[name="' + pair.pair_id +
          '-preference"][value="' + pair.preference + '"]');
        if (pref) { pref.checked = true; }
      }
      var note = form.querySelector('textarea[name="' + pair.pair_id + '-note"]');
      if (note && pair.note) { note.value = pair.note; }
    });
  }
  form.addEventListener("change", function () {
    try { window.localStorage.setItem(storeKey, JSON.stringify(collect())); } catch (e) {}
  });
  document.getElementById("save").addEventListener("click", function () {
    var blob = new Blob([JSON.stringify(collect(), null, 2)], { type: "application/json" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "scores-" + meta.review_id + ".json";
    document.body.appendChild(link); link.click(); link.remove();
  });
  restore();
})();
</script></body></html>
"""


def build_review(
    result_a: dict[str, Any],
    result_b: dict[str, Any],
    page_path: Path,
    key_path: Path,
    *,
    seed: int | None = None,
) -> tuple[int, str]:
    """Write the blind page and its separate key; return (pairs, review id)."""
    if result_a.get("suite_id") != result_b.get("suite_id"):
        raise ValueError("both result files must come from the same suite")
    if result_a.get("system") == result_b.get("system"):
        raise ValueError("compare two different systems")
    rubric = get_rubric(str(result_a.get("task")))
    records_a = {r["item_id"]: r for r in result_a.get("items", []) if "skipped" not in r}
    records_b = {r["item_id"]: r for r in result_b.get("items", []) if "skipped" not in r}
    common = sorted(set(records_a) & set(records_b))
    if not common:
        raise ValueError("the two result files share no runnable item")
    seed_value = seed if seed is not None else secrets.randbits(32)
    shuffler = random.Random(seed_value)
    shuffler.shuffle(common)
    review_id = secrets.token_hex(6)
    pairs_html: list[str] = []
    key_pairs: dict[str, Any] = {}
    pair_ids: list[str] = []
    for number, item_id in enumerate(common, start=1):
        pair_id = f"p{secrets.token_hex(4)}"
        sides = [
            (result_a["system"], records_a[item_id]),
            (result_b["system"], records_b[item_id]),
        ]
        shuffler.shuffle(sides)
        key_pairs[pair_id] = {
            "item_id": item_id,
            "A": {"system": sides[0][0], "run_id": sides[0][1].get("run_id")},
            "B": {"system": sides[1][0], "run_id": sides[1][1].get("run_id")},
        }
        pair_ids.append(pair_id)
        pairs_html.append(
            f"<section class=pair><h2>第 {number} 组</h2><div class=sides>"
            f"<div class=side><h3>A</h3>{_output_html(sides[0][1])}</div>"
            f"<div class=side><h3>B</h3>{_output_html(sides[1][1])}</div></div>"
            f"{_rubric_html(rubric, pair_id)}</section>"
        )
    meta = json.dumps(
        {
            "schema_version": SCORES_SCHEMA,
            "review_id": review_id,
            "suite_id": result_a["suite_id"],
            "pairs": pair_ids,
            "dimensions": [dimension.id for dimension in rubric.dimensions],
        },
        ensure_ascii=True,
    ).replace("<", "\\u003c")
    title = f"盲评：{rubric.title}"
    page = (
        _PAGE.replace("__TITLE__", html.escape(title))
        .replace("__COUNT__", str(len(common)))
        .replace("__HUMAN_ONLY__", html.escape("只有人能判断：" + rubric.human_only))
        .replace("__META__", meta)
        .replace("__PAIRS__", "\n".join(pairs_html))
    )
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page, encoding="utf-8")
    key = {
        "schema_version": KEY_SCHEMA,
        "review_id": review_id,
        "suite_id": result_a["suite_id"],
        "task": result_a.get("task"),
        "seed": seed_value,
        "pairs": key_pairs,
    }
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(common), review_id


def import_scores(scores: dict[str, Any], key: dict[str, Any]) -> HumanScores:
    """Un-blind one exported score file with its key."""
    if scores.get("schema_version") != SCORES_SCHEMA or key.get("schema_version") != KEY_SCHEMA:
        raise ValueError("unexpected score or key file")
    if scores.get("review_id") != key.get("review_id"):
        raise ValueError("score file and key belong to different reviews")
    entries: list[HumanScore] = []
    for pair in scores.get("pairs", []):
        mapping = key["pairs"].get(pair.get("pair_id"))
        if mapping is None:
            continue
        preference = pair.get("preference")
        for side in ("A", "B"):
            dimensions = {
                name: int(value)
                for name, value in (pair.get("dimensions", {}).get(side) or {}).items()
                if isinstance(value, int) and 1 <= value <= 5
            }
            minutes = (pair.get("edit_minutes") or {}).get(side)
            if not dimensions and preference is None and minutes is None:
                continue
            entries.append(
                HumanScore(
                    suite_id=str(key["suite_id"]),
                    item_id=str(mapping["item_id"]),
                    system=str(mapping[side]["system"]),
                    dimensions=dimensions,
                    preferred=None if preference in (None, "tie") else preference == side,
                    edit_minutes=float(minutes) if isinstance(minutes, (int, float)) else None,
                    note=pair.get("note") or None,
                )
            )
    return HumanScores(
        schema_version=HUMAN_SCHEMA,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        scores=entries,
    )
