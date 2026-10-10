#!/usr/bin/env python3
"""Podcast review pilot: offline-preparable Direct vs Agentic comparison.

Validate-only mode probes the video, validates metadata, parses subtitles, and
prints a summary without creating any output. Live mode runs both variants with
the real HarnessKernel against the pinned Qwen provider and writes a RunBundle,
report.json, and index.html per run into a fresh directory outside the repo.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import math
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from vidsnap.config import HarnessConfig
from vidsnap.contracts import Evidence, HarnessPolicy, TerminalState, VideoGoal, VideoSource
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.loopspec import default_loop_spec
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.providers.qwen import QwenProvider
from vidsnap.runtime.context import RunContext
from vidsnap.runtime.kernel import HarnessKernel, KernelRunResult
from vidsnap.runtime.policies import AgenticPolicy, DirectPolicy, default_plugin_registry
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import FFmpegMediaPort, MediaProbe

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_CLIP_SECONDS = 120.0
MAX_FPS2_FRAMES = 250
_TIMESTAMP_RE = re.compile(r"^\[(\d{1,2}):(\d{2}):(\d{2})\]\s*(.+)$")

PILOT_GOAL = (
    "基于所提供的字幕与抽帧证据，输出该播客片段的中文summary以及3到5个claims。"
    "每个claim必须包含text与引用的evidence IDs。"
    "若来源字幕提供了说话者标签则原样保留；未提供时仅称“发言者”，"
    "不要猜测“主持人”“嘉宾”等身份。"
    "ASR在本试用不可用，如调用将被跳过；没有视觉证据时不得描述幻灯片或画面内容。"
    '严格输出JSON：{"summary":"...","claims":[{"text":"...","evidence":[{"evidence_id":"..."}]}]}'
)


@dataclass(frozen=True, slots=True)
class TranscriptEntry:
    start_seconds: float
    end_seconds: float
    text: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_transcript(path: Path, *, source_offset: float, duration: float) -> list[TranscriptEntry]:
    """Select lines whose original timestamp lies in [offset, offset+duration)."""
    parsed: list[tuple[float, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _TIMESTAMP_RE.match(line.strip())
        if not match:
            continue
        t = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + int(match.group(3))
        parsed.append((float(t), match.group(4)))
    parsed.sort(key=lambda item: item[0])
    window_end = source_offset + duration
    entries: list[TranscriptEntry] = []
    for index, (timestamp, text) in enumerate(parsed):
        if not source_offset <= timestamp < window_end:
            continue
        next_time = parsed[index + 1][0] if index + 1 < len(parsed) else window_end
        end = min(next_time, window_end) - source_offset
        entries.append(
            TranscriptEntry(
                start_seconds=timestamp - source_offset,
                end_seconds=end,
                text=text,
            )
        )
    return entries


def validate_clip_metadata(probe: MediaProbe) -> None:
    """Reject clips outside the pilot bounds; never invent a duration."""
    if probe.duration_seconds <= 0:
        raise ValueError("clip has no positive duration")
    if probe.duration_seconds > MAX_CLIP_SECONDS:
        raise ValueError(
            f"clip duration {probe.duration_seconds:.1f}s exceeds the 120s pilot limit"
        )
    if math.ceil(probe.duration_seconds * 2) > MAX_FPS2_FRAMES:
        raise ValueError("clip exceeds the fps=2 frame budget of 250")


def ensure_output_dir(output_dir: Path, *, repo_root: Path) -> None:
    """Refuse repo-internal or already-occupied output directories."""
    resolved = output_dir.resolve()
    if resolved.is_relative_to(repo_root.resolve()):
        raise ValueError("output directory must be outside the repository")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory already exists and is not empty: {output_dir}")


async def validate_only(
    *, video: Path, transcript: Path, source_offset: float, output: Path, media: FFmpegPort
) -> dict[str, object]:
    """Probe and validate inputs; create nothing on disk."""
    ensure_output_dir(output, repo_root=REPO_ROOT)
    probe = await media.probe(video)
    validate_clip_metadata(probe)
    entries = parse_transcript(
        transcript, source_offset=source_offset, duration=probe.duration_seconds
    )
    if not entries:
        raise ValueError("no transcript lines fall inside the clip window")
    return {
        "mode": "validate-only",
        "source_digest": sha256_file(video),
        "source_offset": source_offset,
        "clip": {
            "duration_seconds": probe.duration_seconds,
            "fps": probe.fps,
            "width": probe.width,
            "height": probe.height,
            "has_audio": probe.has_audio,
            "max_frames_at_fps2": math.ceil(probe.duration_seconds * 2),
        },
        "transcript_entries": len(entries),
    }


def preinject_transcript(context: RunContext, entries: list[TranscriptEntry]) -> list[str]:
    """Add the same subtitle Evidence items to one run context (not ASR)."""
    ids: list[str] = []
    for entry in entries:
        evidence_id = context.next_id("transcript")
        context.add(
            Evidence(
                id=evidence_id,
                start_seconds=entry.start_seconds,
                end_seconds=entry.end_seconds,
                modality="transcript",
                content=entry.text,
                budget_class="direct_baseline",
            )
        )
        ids.append(evidence_id)
    return ids


def usage_summary(usage: ProviderUsage | None) -> dict[str, object]:
    """Project provider counters; unknown values stay None, never zero."""
    if usage is None:
        return {
            "model_calls": None,
            "input_bytes": None,
            "input_tokens": None,
            "output_tokens": None,
            "reported": False,
        }
    return {
        "model_calls": usage.model_calls,
        "input_bytes": usage.input_bytes,
        "input_tokens": usage.input_tokens if usage.reported else None,
        "output_tokens": usage.output_tokens if usage.reported else None,
        "reported": usage.reported,
    }


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _load_bundle_evidence(bundle_path: Path) -> list[dict[str, object]]:
    evidence_dir = bundle_path / "evidence"
    if not evidence_dir.is_dir():
        return []
    items: list[dict[str, object]] = []
    for path in sorted(evidence_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append(
            {
                "id": data.get("id", path.stem),
                "start_seconds": data.get("start_seconds", 0),
                "end_seconds": data.get("end_seconds", 0),
                "modality": data.get("modality", ""),
                "content": data.get("content") or "",
            }
        )
    return items


def _load_events(bundle_path: Path) -> list[dict[str, object]]:
    events_file = bundle_path / "events.jsonl"
    if not events_file.is_file():
        return []
    events: list[dict[str, object]] = []
    for line in events_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def render_report(report: dict[str, object], *, clip_name: str) -> str:
    """Render a self-contained XSS-safe Chinese HTML page."""
    source = report.get("source", {})
    synthetic = bool(report.get("synthetic", False))
    variants_data = report.get("variants", {})
    seen_ids: set[object] = set()
    evidence_rows: list[str] = []

    def _row(label: str, item: dict[str, object]) -> str:
        content = item.get("content") or f"[{_esc(item.get('modality', ''))}]"
        return (
            "<tr>"
            f'<td><a href="#clip" data-seek="{_esc(item["start_seconds"])}">'
            f"{_esc(label)}</a></td>"
            f"<td>{_esc(content)}</td>"
            f"<td>{_esc(item['start_seconds'])}s–{_esc(item['end_seconds'])}s</td>"
            "</tr>"
        )

    for item in report.get("evidence", []):
        item_id = str(item.get("id", ""))
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        evidence_rows.append(_row(item_id, item))
    for variant_name in ("direct", "agentic"):
        variant = variants_data.get(variant_name)
        if variant is None:
            continue
        for item in variant.get("evidence", []):
            item_id = str(item.get("id", ""))
            scope_key = (variant_name, item_id)
            if scope_key in seen_ids:
                continue
            seen_ids.add(scope_key)
            evidence_rows.append(_row(f"{variant_name}/{item_id}", item))
    variant_blocks: list[str] = []
    claim_items: list[str] = []
    for name in ("direct", "agentic"):
        variant = variants_data.get(name)
        if variant is None:
            continue
        usage = variant.get("usage", {})
        usage_cells = []
        for key in ("model_calls", "input_bytes", "input_tokens", "output_tokens"):
            value = usage.get(key)
            usage_cells.append(f"{_esc(key)}: {_esc(value) if value is not None else 'unknown'}")
        event_blocks: list[str] = []
        for event in variant.get("events", []):
            payload = event.get("payload")
            payload_html = ""
            if payload:
                payload_html = (
                    "<details><summary>payload</summary><pre>"
                    + _esc(json.dumps(payload, ensure_ascii=False, indent=2))
                    + "</pre></details>"
                )
            call_review = payload.get("call_review") if isinstance(payload, dict) else None
            if call_review is None:
                review_html = "<span>call_review: 未记录</span>"
            else:
                review_html = (
                    "<details><summary>call_review</summary><pre>"
                    + _esc(json.dumps(call_review, ensure_ascii=False, indent=2))
                    + "</pre></details>"
                )
            event_usage = event.get("usage")
            usage_html = ""
            if isinstance(event_usage, dict) and event_usage:
                cells: list[str] = []
                token_keys = ("input_tokens", "output_tokens")
                for key, value in event_usage.items():
                    if key in token_keys and event_usage.get("provider_reported") is False:
                        cells.append(f"{_esc(key)}=unknown")
                    else:
                        cells.append(f"{_esc(key)}={_esc(value)}")
                usage_html = "<span> | " + " ".join(cells) + "</span>"
            duration = event.get("duration_ms")
            event_blocks.append(
                "<li>"
                f"#{_esc(event.get('sequence', '?'))} {_esc(event.get('event_type', ''))} "
                f"[{_esc(event.get('status', ''))}] "
                f"{_esc(duration) if duration is not None else 'unknown'}ms "
                f"{usage_html}{review_html}{payload_html}</li>"
            )
        verification = variant.get("verification")
        gates_html = ""
        if verification:
            gates = verification.get("gates", {})
            gates_html = (
                "<p>verifier gates: "
                + " ".join(f"{_esc(gate)}={'✓' if ok else '✗'}" for gate, ok in gates.items())
                + "</p>"
            )
        frames_value = variant.get("frames")
        latency_value = variant.get("latency_ms")
        frames_text = _esc(frames_value) if frames_value is not None else "unknown"
        latency_text = f"{_esc(latency_value)}ms" if latency_value is not None else "unknown"
        variant_blocks.append(
            f'<div class="variant"><h3>{_esc(name)}</h3>'
            f"<p>terminal: {_esc(variant.get('terminal_state', 'unknown'))}"
            f" | {' | '.join(usage_cells)}"
            f" | frames: {frames_text} | latency: {latency_text}</p>"
            f"{gates_html}"
            f"<ol>{''.join(event_blocks)}</ol></div>"
        )
        output = variant.get("output") or {}
        variant_starts: dict[str, object] = {
            str(item.get("id", "")): item.get("start_seconds", 0)
            for item in list(report.get("evidence", [])) + list(variant.get("evidence", []))
        }
        for claim in output.get("claims", []):
            buttons: list[str] = []
            for ref in claim.get("evidence", []):
                ref_id = str(ref.get("evidence_id", ""))
                seek = _esc(variant_starts.get(ref_id, 0))
                buttons.append(f'<a href="#clip" data-seek="{seek}">{_esc(ref_id)}</a>')
            ref_buttons = " ".join(buttons)
            claim_items.append(
                f"<li><strong>{_esc(name)}</strong>: {_esc(claim.get('text', ''))} "
                f"[{ref_buttons}]</li>"
            )
        summary_text = output.get("summary")
        if summary_text:
            claim_items.append(
                f"<li><strong>{_esc(name)} summary</strong>: {_esc(summary_text)}</li>"
            )
    banner = (
        '<p class="banner">synthetic report — 合成示例，非真实运行结果</p>' if synthetic else ""
    )
    limitation = (
        '<p class="note">限制：claims 仅为对证据 ID 的结构化引用，'
        "verifier 仅校验 schema、时间边界、引用存在性与支持关系，不保证内容语义保真。</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>播客试用对照报告</title>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
.cols {{ display: flex; gap: 2em; }}
.col {{ flex: 1; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; vertical-align: top; }}
.banner {{ background: #fff3cd; padding: 0.5em; }}
.variant {{ margin-bottom: 1em; padding: 1em; background: #f9f9f9; }}
pre {{ white-space: pre-wrap; word-break: break-all; }}
</style>
</head>
<body>
<h1 id="clip">播客试用对照报告</h1>
{banner}
{limitation}
<p>source digest: {_esc(source.get("digest", ""))} |
offset: {_esc(source.get("offset_seconds", ""))}s |
clip: {_esc(source.get("clip_duration", ""))}s</p>
<video id="player" controls width="720"><source src="{_esc(clip_name)}" type="video/mp4"></video>
<div class="cols">
<div class="col">
<h2>证据 notes</h2>
<table><thead><tr><th>ID</th><th>内容</th><th>片段时间</th></tr></thead>
<tbody>{"".join(evidence_rows)}</tbody></table>
<h2>claims</h2>
<ul>{"".join(claim_items)}</ul>
</div>
<div class="col">
<h2>实际事件（按顺序）</h2>
{"".join(variant_blocks)}
</div>
</div>
<script>
document.querySelectorAll('[data-seek]').forEach(function (el) {{
  el.addEventListener('click', function (event) {{
    event.preventDefault();
    var player = document.getElementById('player');
    if (player) {{ player.currentTime = parseFloat(el.getAttribute('data-seek')); }}
  }});
}});
</script>
</body>
</html>"""


async def _run_variant(
    *,
    variant: str,
    source: VideoSource,
    goal: VideoGoal,
    entries: list[TranscriptEntry],
    client: QwenProvider,
    media: FFmpegMediaPort,
    output_dir: Path,
    agentic: bool,
) -> tuple[KernelRunResult, RunBundle]:
    policy = (
        HarnessPolicy(
            tool_mode="agentic",
            max_model_calls=4,
            max_tool_calls=3,
            max_evidence_frames=12,
            max_iterations=3,
        )
        if agentic
        else HarnessPolicy(tool_mode="fixed", max_model_calls=1, max_tool_calls=0)
    )
    bundle = RunBundle.create(
        output_dir / variant,
        loop_spec=default_loop_spec(),
        provider_url=client.identity.base_url,
        provider_identity=client.identity,
    )
    kernel = HarnessKernel(
        policy=AgenticPolicy() if agentic else DirectPolicy(),
        registry=default_plugin_registry(),
    )
    context: RunContext = RunContext(
        source=source,
        policy=policy,
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(goal),
        task_model=client,
        media=media,
        sampler=media.sampler,
        recognizer=None,
        result_writer=bundle.write_result,
        agent_model=client if agentic else None,
    )
    preinject_transcript(context, entries)
    result = await kernel.run(context)
    return result, bundle


async def run_pilot(
    *,
    video: Path,
    transcript: Path,
    source_offset: float,
    output_dir: Path,
    client: QwenProvider,
    media: FFmpegMediaPort,
) -> dict[str, object]:
    """Run Direct then Agentic with real kernels; stop if Direct fails."""
    ensure_output_dir(output_dir, repo_root=REPO_ROOT)
    probe = await media.probe(video)
    validate_clip_metadata(probe)
    entries = parse_transcript(
        transcript, source_offset=source_offset, duration=probe.duration_seconds
    )
    if not entries:
        raise ValueError("no transcript lines fall inside the clip window")
    output_dir.mkdir(parents=True, exist_ok=False)
    digest = sha256_file(video)
    source = VideoSource(path=video, sha256=digest)
    goal = VideoGoal(objective=PILOT_GOAL)
    evidence_payload = [
        {
            "id": f"transcript-{index + 1:03d}",
            "start_seconds": entry.start_seconds,
            "end_seconds": entry.end_seconds,
            "content": entry.text,
        }
        for index, entry in enumerate(entries)
    ]
    report: dict[str, object] = {
        "synthetic": False,
        "goal": PILOT_GOAL,
        "source": {
            "digest": digest,
            "offset_seconds": source_offset,
            "clip_duration": probe.duration_seconds,
            "model": "qwen3.8-max",
            "direct_fps": 2,
            "transcript_digest": sha256_file(transcript),
        },
        "evidence": evidence_payload,
        "variants": {},
    }
    variants: dict[str, object] = report["variants"]  # type: ignore[assignment]

    direct_result, direct_bundle = await _run_variant(
        variant="direct",
        source=source,
        goal=goal,
        entries=entries,
        client=client,
        media=media,
        output_dir=output_dir,
        agentic=False,
    )
    variants["direct"] = _variant_section(direct_result, direct_bundle)

    if direct_result.terminal_state is not TerminalState.SUCCEEDED:
        _write_outputs(output_dir, video, report)
        return report

    agentic_result, agentic_bundle = await _run_variant(
        variant="agentic",
        source=source,
        goal=goal,
        entries=entries,
        client=client,
        media=media,
        output_dir=output_dir,
        agentic=True,
    )
    variants["agentic"] = _variant_section(agentic_result, agentic_bundle)
    _write_outputs(output_dir, video, report)
    return report


def _aggregate_usage(events: list[dict[str, object]]) -> dict[str, object]:
    """Aggregate model.request usage only; missing/unreported counters stay None."""
    model_calls = sum(1 for e in events if e.get("event_type") == "model.request.started")
    terminals = [
        e
        for e in events
        if e.get("event_type")
        in ("model.request.completed", "model.request.failed", "model.request.blocked")
    ]
    input_bytes = 0
    input_tokens = 0
    output_tokens = 0
    bytes_known = True
    tokens_known = True
    for event in terminals:
        usage = event.get("usage")
        if not isinstance(usage, dict) or not usage:
            bytes_known = False
            tokens_known = False
            continue
        bytes_value = usage.get("input_bytes")
        if isinstance(bytes_value, int):
            input_bytes += bytes_value
        else:
            bytes_known = False
        if usage.get("provider_reported"):
            for key, acc in (("input_tokens", "in"), ("output_tokens", "out")):
                value = usage.get(key)
                if isinstance(value, int):
                    if acc == "in":
                        input_tokens += value
                    else:
                        output_tokens += value
                else:
                    tokens_known = False
        else:
            tokens_known = False
    return {
        "model_calls": model_calls,
        "input_bytes": input_bytes if bytes_known and terminals else None,
        "input_tokens": input_tokens if tokens_known and terminals else None,
        "output_tokens": output_tokens if tokens_known and terminals else None,
        "reported": tokens_known and bool(terminals),
    }


def _run_latency_ms(events: list[dict[str, object]]) -> int | None:
    """Latency of the run: terminal event duration, else start-to-terminal offset span."""
    run_start_offset = None
    terminal = None
    for event in events:
        if event.get("event_type") == "run.started":
            offset = event.get("monotonic_offset_ms")
            if isinstance(offset, int):
                run_start_offset = offset
        payload = event.get("payload")
        if isinstance(payload, dict) and "terminal_state" in payload:
            terminal = event
    if terminal is None:
        return None
    duration = terminal.get("duration_ms")
    if isinstance(duration, int):
        return duration
    terminal_offset = terminal.get("monotonic_offset_ms")
    if isinstance(terminal_offset, int) and run_start_offset is not None:
        return terminal_offset - run_start_offset
    return None


def _variant_section(result: KernelRunResult, bundle: RunBundle) -> dict[str, object]:
    events = _load_events(bundle.path)
    bundle_evidence = _load_bundle_evidence(bundle.path)
    frames = sum(1 for item in bundle_evidence if item.get("modality") == "frame")
    latency_ms = _run_latency_ms(events)
    section: dict[str, object] = {
        "run_path": bundle.path.name,
        "terminal_state": result.terminal_state.value,
        "usage": _aggregate_usage(events),
        "events": events,
        "evidence": bundle_evidence,
        "frames": frames,
        "latency_ms": latency_ms,
    }
    if result.verification is not None:
        section["verification"] = {
            "passed": result.verification.passed,
            "gates": dict(result.verification.gates),
        }
    if result.failure_reason:
        section["failure_reason"] = result.failure_reason
    if result.output is not None:
        section["output"] = result.output.model_dump(mode="json")
    return section


def _write_outputs(output_dir: Path, video: Path, report: dict[str, object]) -> None:
    clip_target = output_dir / "clip.mp4"
    if not clip_target.exists():
        shutil.copyfile(video, clip_target)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "index.html").write_text(
        render_report(report, clip_name="clip.mp4"), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Podcast review pilot")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--transcript", required=True, type=Path)
    parser.add_argument("--source-offset", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.validate_only:
            summary = asyncio.run(
                validate_only(
                    video=args.video,
                    transcript=args.transcript,
                    source_offset=args.source_offset,
                    output=args.output,
                    media=FFmpegMediaPort(),
                )
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        ensure_output_dir(args.output, repo_root=REPO_ROOT)
        config = HarnessConfig.from_env()
        report = asyncio.run(
            run_pilot(
                video=args.video,
                transcript=args.transcript,
                source_offset=args.source_offset,
                output_dir=args.output,
                client=QwenProvider(api_key=config.api_key),
                media=FFmpegMediaPort(),
            )
        )
        print(f"pilot complete: {args.output}")
        variants = report.get("variants", {})
        ok = all(
            variants.get(name, {}).get("terminal_state") == TerminalState.SUCCEEDED.value
            for name in ("direct", "agentic")
        )
        return 0 if ok else 1
    except ValueError as exc:
        print(f"pilot validation failed: {exc.__class__.__name__}", file=sys.stderr)
        return 1
    except Exception:
        print("pilot failed with an unexpected error", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
