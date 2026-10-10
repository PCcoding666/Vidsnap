"""Generate the synthetic eval videos from their storyboard specs.

Each ``vidsnap.eval-synthetic/v1`` spec under ``benchmarks/eval/synthetic/`` is
rendered into one MP4: a still slide per entry (Pillow, a local CJK font) with
TTS narration (macOS ``say``), joined with FFmpeg. The spec is the single source
of the reference transcript and slide timing, so references never drift from
the media. Generated files go to the media root and are never committed.

Requirements: macOS ``say`` with the voices named in the specs, FFmpeg with
libx264 and AAC, and Pillow. Usage:

    python scripts/eval/make_synthetic_media.py [--only t3-syn-01] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPECS = ROOT / "benchmarks" / "eval" / "synthetic"
DEFAULT_MEDIA = ROOT / "benchmarks" / "eval" / "media"
FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)
LEAD_SECONDS = 0.4
TAIL_SECONDS = 0.3


def find_font() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    raise SystemExit("no CJK font found; install one of: " + ", ".join(FONT_CANDIDATES))


def wrap(text: str, font: object, max_width: int) -> list[str]:
    """Greedy wrap by measured width; CJK text wraps per character."""
    lines: list[str] = []
    current = ""
    for character in text:
        trial = current + character
        if font.getlength(trial) > max_width and current:  # type: ignore[attr-defined]
            lines.append(current)
            current = character.lstrip()
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def render_slide(lines: list[str], width: int, height: int, font_path: str, out: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, height), (250, 248, 242))
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(font_path, max(24, height // 14))
    body_font = ImageFont.truetype(font_path, max(18, height // 22))
    margin = width // 14
    y = height // 10
    draw.rectangle([0, 0, width, height // 60], fill=(40, 70, 120))
    for index, text in enumerate(lines):
        font = title_font if index == 0 else body_font
        colour = (40, 70, 120) if index == 0 else (30, 30, 34)
        for line in wrap(text, font, width - 2 * margin):
            draw.text((margin, y), line, font=font, fill=colour)
            y += int(font.size * 1.45)
        y += int(body_font.size * 0.5)
    image.save(out)


def tts(text: str, voice: str, out: Path) -> None:
    subprocess.run(["say", "-v", voice, "-o", str(out), text], check=True)


def duration(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(completed.stdout.strip())


def segment(slide_png: Path, narration: Path, seconds: float, out: Path) -> None:
    delay = int(LEAD_SECONDS * 1000)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "10",
            "-i",
            str(slide_png),
            "-i",
            str(narration),
            "-filter_complex",
            f"[1:a]aresample=44100,adelay={delay},apad[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-t",
            f"{seconds:.3f}",
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "10",
            "-c:a",
            "aac",
            "-ac",
            "1",
            "-b:a",
            "64k",
            "-threads",
            "1",
            "-map_metadata",
            "-1",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            str(out),
        ],
        check=True,
    )


def concat(segments: list[Path], out: Path, work: Path) -> None:
    listing = work / "segments.txt"
    listing.write_text("".join(f"file '{path}'\n" for path in segments), encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-map_metadata",
            "-1",
            "-fflags",
            "+bitexact",
            "-movflags",
            "+faststart",
            str(out),
        ],
        check=True,
    )


def build(spec_path: Path, media_root: Path, font: str, *, force: bool) -> dict[str, object]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out = media_root / spec["output"]
    if out.is_file() and not force:
        return {"id": spec["id"], "path": str(out), "status": "exists"}
    too_long: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vidsnap-synthetic-") as temporary:
        work = Path(temporary)
        segments: list[Path] = []
        for index, slide in enumerate(spec["slides"]):
            png = work / f"slide-{index:02d}.png"
            audio = work / f"slide-{index:02d}.aiff"
            render_slide(slide["lines"], spec["width"], spec["height"], font, png)
            tts(slide["narration"], slide.get("voice") or spec["voice"], audio)
            spoken = duration(audio)
            needed = spoken + LEAD_SECONDS + TAIL_SECONDS
            planned = slide["duration_seconds"]
            if needed > planned:
                too_long.append(f"slide {index}: needs {needed:.1f} s > {planned}")
                continue
            clip = work / f"segment-{index:02d}.mp4"
            segment(png, audio, float(slide["duration_seconds"]), clip)
            segments.append(clip)
        if too_long:
            raise SystemExit(f"{spec['id']}: narration does not fit: " + "; ".join(too_long))
        concat(segments, out, work)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    return {
        "id": spec["id"],
        "path": str(out),
        "status": "generated",
        "sha256": digest,
        "bytes": out.stat().st_size,
        "duration_seconds": round(duration(out), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--specs", type=Path, default=DEFAULT_SPECS)
    parser.add_argument("--media-root", type=Path, default=DEFAULT_MEDIA)
    parser.add_argument("--only", default="", help="Comma-separated spec ids.")
    parser.add_argument("--force", action="store_true", help="Regenerate existing files.")
    arguments = parser.parse_args()
    missing = [tool for tool in ("say", "ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        print(f"missing tools: {', '.join(missing)} (macOS say + FFmpeg are required)")
        return 2
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is required: pip install pillow")
        return 2
    font = find_font()
    wanted = {part.strip() for part in arguments.only.split(",") if part.strip()}
    results = []
    for spec_path in sorted(arguments.specs.glob("*.json")):
        if wanted and spec_path.stem not in wanted:
            continue
        results.append(build(spec_path, arguments.media_root, font, force=arguments.force))
        print(json.dumps(results[-1], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
