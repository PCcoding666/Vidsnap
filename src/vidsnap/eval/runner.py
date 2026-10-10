"""Run one suite against one system: kernel run, index line, render, grade, attribute, cost.

Each item is one ordinary RunBundle under the runs root, appended to the run
index like any CLI run. The results file (``vidsnap.eval-result/v1``) is
rewritten after every item so an interrupted suite keeps what it measured.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import JsonValue

from vidsnap import __version__
from vidsnap.contracts import HarnessPolicy, VideoSource, default_loop_spec
from vidsnap.eval.adapters import FakeMedia
from vidsnap.eval.attribution import read_evidence, stage_metrics
from vidsnap.eval.costs import LoadedEvalPrices, run_cost
from vidsnap.eval.graders import grade_output
from vidsnap.eval.render import make_frame_resolver, render_output
from vidsnap.eval.suite import EvalItem, LoadedSuite, file_sha256, resolve_media
from vidsnap.eval.systems import BuildOptions, NotApplicable, SystemSpec, build_components
from vidsnap.eval.tasks import PROMPT_VERSION, EvalOutput, get_task
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.runtime import HarnessKernel, RecipeIdentity, RunContext, default_plugin_registry
from vidsnap.trace.run_index import append_index_record, summarize_run
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import FFmpegMediaPort
from vidsnap.video.sampling import AdaptiveSampler

RESULT_SCHEMA = "vidsnap.eval-result/v1"
MediaMode = Literal["real", "fake"]


@dataclass(slots=True)
class RunOptions:
    """Everything one ``vidsnap eval run`` invocation fixes before the first item."""

    suite: LoadedSuite
    system: SystemSpec
    media_root: Path
    runs_root: Path
    out_dir: Path
    item_ids: tuple[str, ...] | None = None
    limit: int | None = None
    prices: LoadedEvalPrices | None = None
    max_cost: float | None = None
    media_mode: MediaMode = "real"
    render_check: bool = False
    build: BuildOptions = field(default_factory=BuildOptions)
    policy: HarnessPolicy = field(default_factory=HarnessPolicy)
    media_factory: Callable[[EvalItem, float], FFmpegPort] | None = None
    progress: Callable[[str], None] | None = None
    item_root: Path | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _expected_duration(options: RunOptions, item: EvalItem) -> float | None:
    if item.source.clip is not None:
        return item.source.clip.end_seconds - item.source.clip.start_seconds
    spec = options.suite.specs.get(item.item_id)
    if spec is not None:
        return spec.duration_seconds()
    return item.source.duration_seconds


def _cut_clip(source: Path, item: EvalItem, cache: Path) -> Path:
    clip = item.source.clip
    assert clip is not None
    output = cache / f"{item.item_id}-{clip.start_seconds:g}-{clip.end_seconds:g}.mp4"
    if output.is_file():
        return output
    cache.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-ss",
            f"{clip.start_seconds:.3f}",
            "-to",
            f"{clip.end_seconds:.3f}",
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            str(output),
        ],
        capture_output=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("clip extraction failed")
    return output


def _skip(item: EvalItem, reason: str) -> dict[str, JsonValue]:
    return {"item_id": item.item_id, "item_status": item.status, "skipped": reason}


async def run_item(options: RunOptions, item: EvalItem) -> dict[str, JsonValue]:
    """Run, record, render and grade one item; never raises for one item's failure."""
    task = get_task(options.suite.suite.task)
    spec = options.system
    if item.status == "placeholder":
        return _skip(item, "placeholder")
    media_path = resolve_media(item, options.media_root)
    duration = _expected_duration(options, item)
    source_sha: str | None = None
    if options.media_mode == "real":
        if media_path is None or not media_path.is_file():
            return _skip(item, "media_missing")
        source_sha = file_sha256(media_path)
        if item.source.sha256 is not None and source_sha != item.source.sha256:
            if item.source.kind != "synthetic":
                return _skip(item, "sha256_mismatch")
        if item.source.clip is not None:
            media_path = _cut_clip(media_path, item, options.out_dir / "_clips")
        media: FFmpegPort = (
            options.media_factory(item, duration or 0.0)
            if options.media_factory is not None
            else FFmpegMediaPort()
        )
    else:
        if duration is None:
            return _skip(item, "duration_unknown_for_fake_media")
        media = (
            options.media_factory(item, duration)
            if options.media_factory is not None
            else FakeMedia(duration_seconds=duration, has_audio=item.source.has_audio is not False)
        )
    try:
        components = build_components(spec, task, item, media=media, options=options.build)
    except NotApplicable as reason:
        return _skip(item, f"not_applicable: {reason}")
    run_dir = options.runs_root / str(uuid.uuid4())
    identity = components.provider_identity
    bundle = RunBundle.create(
        run_dir,
        loop_spec=default_loop_spec(),
        provider_url=identity.base_url,
        provider_identity=identity,
    )
    source_path = media_path if media_path is not None else Path(item.item_id)
    context: RunContext[Any, Any] = RunContext(
        source=VideoSource(path=source_path),
        policy=options.policy,
        bundle=bundle,
        task_adapter=components.adapter,
        task_model=components.task_model,
        media=components.media,
        sampler=AdaptiveSampler(),
        recognizer=components.recognizer,
        result_writer=bundle.write_result,
        provider_identity=identity,
        speech_recognizer_identity=components.recognizer_identity,
        recipe=RecipeIdentity(id=f"eval/{options.suite.suite.task}", version=PROMPT_VERSION),
    )
    kernel: HarnessKernel[Any, Any] = HarnessKernel(
        policy=components.policy, registry=default_plugin_registry()
    )
    result = await kernel.run(context)
    record: dict[str, JsonValue] = {"item_id": item.item_id, "item_status": item.status}
    try:
        record.update(_finish_item(options, item, task, result.output, run_dir, media_path))
    except Exception as error:
        record["eval_error"] = type(error).__name__
    record["terminal_state"] = result.terminal_state.value
    record["source_sha256"] = source_sha
    record["source_sha256_matches"] = (
        source_sha == item.source.sha256
        if source_sha is not None and item.source.sha256 is not None
        else None
    )
    return record


def _finish_item(
    options: RunOptions,
    item: EvalItem,
    task: Any,
    output: EvalOutput | None,
    run_dir: Path,
    media_path: Path | None,
) -> dict[str, JsonValue]:
    command = f"eval run {options.suite.suite.suite_id} {options.system.name}"
    summary = summarize_run(
        run_dir,
        command=command,
        price_table=options.prices.run_index_table() if options.prices is not None else None,
    )
    append_index_record(options.runs_root, summary)
    duration_value = summary.get("input_duration_seconds")
    duration = (
        float(duration_value)
        if isinstance(duration_value, (int, float))
        else (_expected_duration(options, item) or 0.0)
    )
    grade = grade_output(task, output, item, duration)
    render: dict[str, JsonValue] = {}
    if output is not None:
        evidence = read_evidence(run_dir)
        resolver = make_frame_resolver(
            evidence, media_path if options.media_mode == "real" else None
        )
        item_dir = (options.item_root or options.out_dir) / item.item_id
        render = render_output(output, item_dir, resolver, check_render=options.render_check)
        render["dir"] = str(item_dir)
        for key in ("html_valid", "render_ok"):
            if key in render:
                grade[key] = render[key]
    stages = stage_metrics(run_dir, item, grade, harness=options.system.kind == "harness")
    return {
        "run_id": summary.get("run_id"),
        "bundle_path": summary.get("bundle_path"),
        "failure_category": summary.get("failure_category"),
        "failure_reason": summary.get("failure_reason"),
        "http_status": summary.get("http_status"),
        "duration_ms": summary.get("duration_ms"),
        "input_duration_seconds": summary.get("input_duration_seconds"),
        "model_calls": summary.get("model_calls"),
        "tool_calls": summary.get("tool_calls"),
        "input_tokens": summary.get("input_tokens"),
        "output_tokens": summary.get("output_tokens"),
        "tokens_reported": summary.get("tokens_reported"),
        "failed_gates": summary.get("failed_gates"),
        "cost": run_cost(run_dir, options.prices),
        "machine": grade,
        "stages": stages,
        "render": render,
    }


def results_path(options: RunOptions, started: str) -> Path:
    stamp = started.replace(":", "").replace("-", "").split(".")[0].rstrip("Z") + "Z"
    return options.out_dir / f"{options.suite.suite.suite_id}__{options.system.slug}__{stamp}.json"


async def run_suite(options: RunOptions) -> tuple[Path, dict[str, JsonValue]]:
    """Run the selected items in order, stopping at the spending cap."""
    started = _utc_now()
    suite = options.suite.suite
    items = [
        item for item in suite.items if options.item_ids is None or item.item_id in options.item_ids
    ]
    if options.item_ids is not None:
        unknown = set(options.item_ids) - {item.item_id for item in suite.items}
        if unknown:
            raise ValueError(f"unknown item ids: {', '.join(sorted(unknown))}")
    if options.limit is not None:
        runnable = [item for item in items if item.status != "placeholder"]
        items = runnable[: options.limit]
    options.out_dir = options.out_dir.resolve()
    options.runs_root = options.runs_root.resolve()
    path = results_path(options, started)
    options.item_root = path.with_suffix("")
    document: dict[str, JsonValue] = {
        "schema_version": RESULT_SCHEMA,
        "suite_id": suite.suite_id,
        "suite_path": str(options.suite.path),
        "suite_sha256": options.suite.sha256,
        "task": suite.task,
        "system": options.system.name,
        "system_kind": options.system.kind,
        "model": options.system.model,
        "base_system": options.system.base_name,
        "package_version": __version__,
        "prompt_version": PROMPT_VERSION,
        "media_mode": options.media_mode,
        "endpoint": options.build.endpoint,
        "runs_root": str(options.runs_root),
        "out_dir": str(options.item_root),
        "price_table_sha256": options.prices.sha256 if options.prices is not None else None,
        "currency": options.prices.table.currency if options.prices is not None else None,
        "max_cost": options.max_cost,
        "spent": 0.0 if options.prices is not None else None,
        "started_at": started,
        "finished_at": None,
        "stopped_reason": None,
        "items": [],
    }
    records: list[JsonValue] = []
    spent = 0.0
    stopped: str | None = None
    for item in items:
        if stopped is not None:
            records.append(_skip(item, stopped))
            continue
        if options.progress is not None:
            options.progress(f"{item.item_id}: running {options.system.name}")
        record = await run_item(options, item)
        records.append(record)
        cost = record.get("cost")
        if not options.system.mock and options.prices is not None and "skipped" not in record:
            amount = cost.get("amount") if isinstance(cost, dict) else None
            if not isinstance(amount, (int, float)):
                stopped = "cost_unknown"
            else:
                spent += float(amount)
                if options.max_cost is not None and spent >= options.max_cost:
                    stopped = "budget_cap_reached"
        document["items"] = list(records)
        document["spent"] = round(spent, 6) if options.prices is not None else None
        document["stopped_reason"] = stopped
        _write_json(path, document)
        if options.progress is not None:
            state = record.get("terminal_state") or record.get("skipped")
            options.progress(f"{item.item_id}: {state}")
    document["items"] = list(records)
    document["finished_at"] = _utc_now()
    document["stopped_reason"] = stopped
    _write_json(path, document)
    return path, document


def live_system_needs_budget(spec: SystemSpec) -> bool:
    return not spec.mock


__all__ = ["RESULT_SCHEMA", "RunOptions", "live_system_needs_budget", "run_item", "run_suite"]
