"""Render task outputs to reviewable files: Markdown, JSON, timeline HTML and SRT.

Figures are resolved the same way for every system: a cited harness frame is
copied from the RunBundle; any other timestamp is extracted locally from the
source video, so a human compares content, not image availability.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import tempfile
import zlib
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from vidsnap.contracts import Evidence
from vidsnap.eval.tasks import (
    ArticleOutput,
    ArticleSection,
    ClipReviewOutput,
    EvalOutput,
    Figure,
    LessonOutput,
    StoryboardOutput,
)
from vidsnap.eval.text import format_clock

FrameResolver = Callable[[Figure, Path], Path | None]


def make_frame_resolver(
    evidence: list[Evidence], media: Path | None, *, ffmpeg: str = "ffmpeg"
) -> FrameResolver:
    """Copy a cited bundle frame, else extract the timestamp from the source video."""
    frames = {
        item.id: item.artifact_path
        for item in evidence
        if item.modality == "frame" and item.artifact_path is not None
    }
    can_extract = media is not None and media.is_file() and shutil.which(ffmpeg) is not None

    def resolve(figure: Figure, destination: Path) -> Path | None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        cited = frames.get(figure.evidence_id or "")
        if cited is not None and cited.is_file() and cited.stat().st_size > 64:
            shutil.copyfile(cited, destination)
            return destination
        if not can_extract or media is None or figure.timestamp_seconds < 0:
            return None
        completed = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-ss",
                f"{figure.timestamp_seconds:.3f}",
                "-i",
                str(media),
                "-frames:v",
                "1",
                "-vf",
                "scale='min(960,iw)':-2",
                "-q:v",
                "3",
                str(destination),
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0 or not destination.is_file():
            return None
        return destination

    return resolve


def _figure_markdown(figure: Figure, image: Path | None, out_dir: Path) -> list[str]:
    stamp = format_clock(figure.timestamp_seconds)
    lines: list[str] = []
    if image is not None:
        lines.append(f"![{figure.caption}]({image.relative_to(out_dir).as_posix()})")
    else:
        lines.append(f"[画面 {stamp} 未能导出]")
    lines.append(f"*图：{figure.caption}（{stamp}）*")
    return lines


def _sections_markdown(
    sections: list[ArticleSection], out_dir: Path, resolver: FrameResolver, counter: list[int]
) -> list[str]:
    lines: list[str] = []
    for section in sections:
        lines += [f"## {section.heading}", "", section.body, ""]
        for figure in section.figures:
            counter[0] += 1
            image = resolver(figure, out_dir / "images" / f"fig-{counter[0]:02d}.jpg")
            lines += [*_figure_markdown(figure, image, out_dir), ""]
    return lines


def article_markdown(output: ArticleOutput, out_dir: Path, resolver: FrameResolver) -> str:
    counter = [0]
    lines = [f"# {output.title}", "", output.intro, "", "## 核心要点", ""]
    lines += [f"{index}. {point}" for index, point in enumerate(output.takeaways, start=1)]
    lines.append("")
    lines += _sections_markdown(output.sections, out_dir, resolver, counter)
    lines += ["## 总结", "", output.summary, ""]
    return "\n".join(lines)


def review_markdown(output: ClipReviewOutput) -> str:
    lines = ["# 片段点评", "", output.summary, "", "## 观点", ""]
    for claim in output.claims:
        span = f"{format_clock(claim.start_seconds)}–{format_clock(claim.end_seconds)}"
        lines.append(f"- [{span}] {claim.text}")
    return "\n".join(lines) + "\n"


def notes_markdown(output: LessonOutput, out_dir: Path, resolver: FrameResolver) -> str:
    counter = [0]
    notes = output.notes
    lines = [f"# {notes.title}", ""]
    lines += _sections_markdown(notes.sections, out_dir, resolver, counter)
    lines += ["## 总结", "", notes.summary, "", "## 错题", ""]
    for index, question in enumerate(output.wrong_questions, start=1):
        lines += [f"### 第 {index} 题（{format_clock(question.frame_timestamp_seconds)}）", ""]
        lines.append(question.stem)
        lines += [f"- {option}" for option in question.options]
        lines += ["", f"**正确答案**：{question.correct_answer}", ""]
        lines += [f"**常见错误**：{question.common_mistake}", "", "**解题步骤**：", ""]
        lines += [f"{step_no}. {step}" for step_no, step in enumerate(question.solution_steps, 1)]
        lines += ["", f"**知识点**：{'、'.join(question.knowledge_points)}", ""]
    return "\n".join(lines)


def captions_srt(storyboard: StoryboardOutput) -> str:
    """SRT generated from the storyboard's captions, the single caption source."""

    def stamp(seconds: float) -> str:
        millis = max(0, int(round(seconds * 1000)))
        return (
            f"{millis // 3_600_000:02d}:{millis % 3_600_000 // 60_000:02d}:"
            f"{millis % 60_000 // 1000:02d},{millis % 1000:03d}"
        )

    captions = sorted(
        (caption for scene in storyboard.scenes for caption in scene.captions),
        key=lambda caption: caption.start_seconds,
    )
    blocks = [
        f"{index}\n{stamp(caption.start_seconds)} --> {stamp(caption.end_seconds)}\n"
        f"{caption.text}\n"
        for index, caption in enumerate(captions, start=1)
    ]
    return "\n".join(blocks)


def script_markdown(storyboard: StoryboardOutput) -> str:
    lines = [f"# {storyboard.title}", ""]
    for scene in storyboard.scenes:
        span = f"{format_clock(scene.start_seconds)}–{format_clock(scene.end_seconds)}"
        lines += [f"## {scene.title}（{span}）", ""]
        if scene.visual:
            lines += [f"画面：{scene.visual}", ""]
        lines += [
            f"- [{format_clock(caption.start_seconds)}] {caption.text}"
            for caption in scene.captions
        ]
        lines.append("")
    return "\n".join(lines)


_HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root { --bg:#111418; --ink:#f2efe8; --muted:#9aa3ad; --accent:#f4d345; }
html,body { margin:0; background:var(--bg); color:var(--ink);
  font-family:"PingFang SC","Hiragino Sans GB","Noto Sans CJK SC",sans-serif; }
#stage { position:relative; width:min(100vw,177.78vh); aspect-ratio:16/9; margin:0 auto;
  overflow:hidden; background:var(--bg); }
#scene-title { position:absolute; top:7%; left:6%; right:6%; font-size:4.2vmin;
  color:var(--accent); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
#on-screen { position:absolute; top:22%; left:6%; right:6%; font-size:3.4vmin; line-height:1.6; }
#visual { position:absolute; top:70%; left:6%; right:6%; font-size:2vmin; color:var(--muted); }
#caption { position:absolute; bottom:4%; left:8%; right:8%; text-align:center;
  font-size:3vmin; background:rgba(0,0,0,.55); padding:.6vmin 1vmin; border-radius:.6vmin; }
#controls { display:flex; gap:8px; align-items:center; justify-content:center; padding:8px; }
#controls input { width:60%; }
.fade { transition:opacity .6s ease; }
</style>
</head>
<body>
<div id="stage">
  <div id="scene-title" class="fade"></div>
  <div id="on-screen" class="fade"></div>
  <div id="visual" class="fade"></div>
  <div id="caption"></div>
</div>
<div id="controls">
  <button id="play" type="button">播放/暂停</button>
  <input id="seek" type="range" min="0" step="0.1" value="0">
  <span id="clock">0.0s</span>
</div>
<script type="application/json" id="storyboard">__DATA__</script>
<script>
(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("storyboard").textContent);
  var scenes = data.scenes;
  var captionItems = [];
  scenes.forEach(function (scene) {
    scene.captions.forEach(function (c) { captionItems.push(c); });
  });
  var total = scenes.reduce(function (m, s) { return Math.max(m, s.end_seconds); }, 0);
  var seek = document.getElementById("seek");
  seek.max = String(total);
  var params = new URLSearchParams(window.location.search);
  var t = Math.max(0, Math.min(total, parseFloat(params.get("t") || "0") || 0));
  var playing = !params.has("t");
  var last = null;
  function at(list, time) {
    for (var i = 0; i < list.length; i++) {
      if (time >= list[i].start_seconds && time < list[i].end_seconds) { return list[i]; }
    }
    return null;
  }
  function draw() {
    var scene = at(scenes, t);
    var caption = at(captionItems, t);
    document.getElementById("scene-title").textContent = scene ? scene.title : "";
    var list = document.getElementById("on-screen");
    list.textContent = "";
    if (scene) {
      scene.on_screen_text.forEach(function (line) {
        var div = document.createElement("div");
        div.textContent = line;
        list.appendChild(div);
      });
    }
    document.getElementById("visual").textContent = scene ? scene.visual : "";
    document.getElementById("caption").textContent = caption ? caption.text : "";
    document.getElementById("clock").textContent = t.toFixed(1) + "s / " + total.toFixed(1) + "s";
    seek.value = String(t);
  }
  function tick(now) {
    if (last !== null && playing) { t = Math.min(total, t + (now - last) / 1000); }
    last = now;
    draw();
    if (t >= total) { playing = false; }
    window.requestAnimationFrame(tick);
  }
  document.getElementById("play").addEventListener("click", function () { playing = !playing; });
  seek.addEventListener("input", function () { t = parseFloat(seek.value) || 0; draw(); });
  draw();
  window.requestAnimationFrame(tick);
})();
</script>
</body>
</html>
"""


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def storyboard_html(storyboard: StoryboardOutput) -> str:
    """One self-contained timeline page: one scene list, one clock, one caption source."""
    data = json.dumps(storyboard.model_dump(mode="json"), ensure_ascii=False)
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return _HTML_TEMPLATE.replace("__TITLE__", _escape_html(storyboard.title)).replace(
        "__DATA__", data
    )


class _IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)


def html_valid(html: str) -> bool:
    """The page parses and carries the stage, caption and storyboard data elements."""
    collector = _IdCollector()
    try:
        collector.feed(html)
        collector.close()
    except Exception:
        return False
    if not {"stage", "caption", "storyboard"} <= collector.ids:
        return False
    start = html.find('id="storyboard">')
    end = html.find("</script>", start)
    try:
        json.loads(html[start + len('id="storyboard">') : end])
    except (ValueError, json.JSONDecodeError):
        return False
    return True


def find_chrome() -> str | None:
    for candidate in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ):
        if Path(candidate).is_file() or shutil.which(candidate):
            return candidate
    return None


def render_check(
    html_path: Path, *, at_seconds: float = 3.0, chrome: str | None = None
) -> bool | None:
    """Headless-render one frame with every host name unresolvable; None when no browser."""
    browser = chrome or find_chrome()
    if browser is None:
        return None
    with tempfile.TemporaryDirectory(prefix="vidsnap-render-") as profile:
        screenshot = Path(profile) / "frame.png"
        completed = subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={profile}",
                "--host-resolver-rules=MAP * ~NOTFOUND",
                "--window-size=1280,800",
                "--virtual-time-budget=2000",
                f"--screenshot={screenshot}",
                f"{html_path.resolve().as_uri()}?t={at_seconds:.1f}",
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0 or not screenshot.is_file():
            return False
        return png_is_not_blank(screenshot.read_bytes())


def _png_pixels(data: bytes) -> tuple[int, int, int, bytes] | None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    width = height = bit_depth = color_type = interlace = 0
    idat = bytearray()
    while offset + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[offset : offset + 8])
        body = data[offset + 8 : offset + 8 + length]
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.extend(body)
        elif kind == b"IEND":
            break
        offset += 12 + length
    channels = {2: 3, 6: 4}.get(color_type)
    if channels is None or bit_depth != 8 or interlace != 0 or not width or not height:
        return None
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    pixels = bytearray()
    previous = bytearray(stride)
    position = 0
    for _ in range(height):
        filter_type = raw[position]
        line = bytearray(raw[position + 1 : position + 1 + stride])
        position += 1 + stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                line[index] = (line[index] + left) & 0xFF
            elif filter_type == 2:
                line[index] = (line[index] + up) & 0xFF
            elif filter_type == 3:
                line[index] = (line[index] + (left + up) // 2) & 0xFF
            elif filter_type == 4:
                estimate = left + up - upper_left
                pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - upper_left)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else upper_left
                line[index] = (line[index] + predictor) & 0xFF
        pixels.extend(line)
        previous = line
    return width, height, channels, bytes(pixels)


def png_is_not_blank(data: bytes, *, threshold: float = 0.002) -> bool:
    """True when more than ``threshold`` of pixels differ from the most common colour."""
    decoded = _png_pixels(data)
    if decoded is None:
        return False
    width, height, channels, pixels = decoded
    counts: dict[bytes, int] = {}
    step = max(1, (width * height) // 200_000)
    total = 0
    for index in range(0, width * height, step):
        colour = pixels[index * channels : index * channels + 3]
        counts[colour] = counts.get(colour, 0) + 1
        total += 1
    if not total:
        return False
    return 1 - max(counts.values()) / total > threshold


def render_output(
    output: EvalOutput,
    out_dir: Path,
    resolver: FrameResolver,
    *,
    check_render: bool = False,
) -> dict[str, JsonValue]:
    """Write the reviewable files for one output and report HTML checks."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, JsonValue] = {}
    storyboard: StoryboardOutput | None = None
    payload: Any = output.model_dump(mode="json")
    (out_dir / "output.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if isinstance(output, ArticleOutput):
        (out_dir / "article.md").write_text(
            article_markdown(output, out_dir, resolver), encoding="utf-8"
        )
    elif isinstance(output, ClipReviewOutput):
        (out_dir / "review.md").write_text(review_markdown(output), encoding="utf-8")
    elif isinstance(output, StoryboardOutput):
        storyboard = output
    elif isinstance(output, LessonOutput):
        questions = [question.model_dump(mode="json") for question in output.wrong_questions]
        (out_dir / "wrong_questions.json").write_text(
            json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "notes.md").write_text(
            notes_markdown(output, out_dir, resolver), encoding="utf-8"
        )
        storyboard = output.video
    if storyboard is not None:
        html = storyboard_html(storyboard)
        html_path = out_dir / "video.html"
        html_path.write_text(html, encoding="utf-8")
        srt = captions_srt(storyboard)
        (out_dir / "captions.srt").write_text(srt, encoding="utf-8")
        (out_dir / "script.md").write_text(script_markdown(storyboard), encoding="utf-8")
        report["html_valid"] = html_valid(html)
        caption_count = sum(len(scene.captions) for scene in storyboard.scenes)
        report["srt_matches_captions"] = srt.count(" --> ") == caption_count
        report["render_ok"] = render_check(html_path) if check_render else None
    report["images"] = (
        sum(1 for _ in (out_dir / "images").glob("*.jpg")) if (out_dir / "images").is_dir() else 0
    )
    files: list[JsonValue] = [*sorted(p.name for p in out_dir.iterdir() if p.is_file())]
    report["files"] = files
    return report
