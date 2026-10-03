#!/usr/bin/env python3
"""Native-video two-route review: Bailian native audiovisual vs bounded Harness.

Validate-only mode probes real media, checks hashes, offset bounds, local ASR
dependencies, and the inline Base64 budget without any model or ASR inference
and without creating output. Live mode runs the native route first — failure
keeps the safe record and stops — then the bounded agentic Harness route with
qwen3.8-max, the two registered tools, and a real local Whisper recognizer.
Both routes record real RunBundles with traced start/finish event pairs and an
allowlisted runtime-configuration event. Outputs go to a fresh directory
outside every linked repository checkout.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import math
import mimetypes
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import JsonValue

import vidsnap
from vidsnap.contracts import HarnessPolicy, TerminalState, VideoGoal, VideoSource
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.loopspec import LoopBudgets, LoopSpec
from vidsnap.contracts.models import StrictModel
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.loop.state_machine import BudgetExceeded
from vidsnap.loop.trace_recorder import TraceRecorder
from vidsnap.plugins.base import TranscriptionPort, TranscriptionResponse
from vidsnap.plugins.registry import PluginRegistry
from vidsnap.providers.local_whisper import (
    LocalWhisperExecution,
    LocalWhisperTranscriber,
    WhisperRunner,
)
from vidsnap.providers.native_video import (
    MAX_INLINE_BASE64_BYTES,
    NativeClip,
    NativeVideoClient,
    NativeVideoError,
)
from vidsnap.providers.qwen import QwenProvider
from vidsnap.runtime.context import RunContext
from vidsnap.runtime.kernel import HarnessKernel, KernelRunResult
from vidsnap.runtime.policies import default_plugin_registry
from vidsnap.tasks.video_analysis import VideoAnalysisTaskAdapter
from vidsnap.trace.export import export_trace
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import FFmpegMediaPort, MediaProbe

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_CLIP_SECONDS = 120.0

COMMON_TASK = (
    "请基于这段视频的实际音画内容，输出忠实于原意的中文笔记和一段简短摘要。"
    "笔记中的关键论述必须附带片内时间引用（格式 [MM:SS]）。"
    "仅依据你实际看到和听到的内容作答；不得根据标题、文件名或常识猜测未出现的内容。"
)

REGISTERED_TOOLS = ["transcribe_audio", "sample_evidence"]
# Native route: one bounded request, no tools, its own wall deadline. The
# LoopBudgets contract cannot express "frames unknown", so the frame cap is
# pinned at the contract minimum and the limitations note states that the
# native route is not subject to the Harness frame budget at all.
NATIVE_BUDGETS = {
    "max_model_calls": 1,
    "max_tool_calls": 0,
    "max_evidence_frames": 1,
    "max_wall_seconds": 300,
}
HARNESS_BUDGETS = {
    "max_model_calls": 6,
    "max_tool_calls": 4,
    "max_evidence_frames": 24,
    "max_wall_seconds": 900,
}

_BROWSER_PLAYABLE_SUFFIXES = {".mp4", ".m4v", ".webm", ".ogv", ".mov"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def task_hash() -> str:
    return hashlib.sha256(COMMON_TASK.encode("utf-8")).hexdigest()


def default_forbidden_roots() -> tuple[Path, ...]:
    """All linked git worktree checkouts; fails closed when git is unusable."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=REPO_ROOT,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("cannot enumerate git worktrees; refusing to validate") from error
    if result.returncode != 0:
        raise ValueError("cannot enumerate git worktrees; refusing to validate")
    roots = [REPO_ROOT.resolve()]
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            roots.append(Path(line[len("worktree ") :]).resolve())
    return tuple(dict.fromkeys(roots))


def ensure_output_dir(output_dir: Path, *, forbidden_roots: tuple[Path, ...]) -> None:
    """Refuse repo-internal (incl. symlinked) or already-existing output dirs."""
    resolved = output_dir.resolve()
    for root in forbidden_roots:
        if resolved.is_relative_to(root.resolve()):
            raise ValueError("output directory must be outside every repository checkout")
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")


def _validate_whisper_dependencies(executable: Path, model: Path) -> None:
    """Check local ASR dependency paths only; never run inference here."""
    if not executable.is_file():
        raise ValueError(f"whisper executable does not exist: {executable}")
    if not model.is_file() or model.stat().st_size == 0:
        raise ValueError(f"whisper model file missing or empty: {model}")


def _validate_clip_probe(probe: MediaProbe) -> None:
    if not math.isfinite(probe.duration_seconds) or probe.duration_seconds <= 0:
        raise ValueError("clip has no positive finite duration")
    if probe.duration_seconds > MAX_CLIP_SECONDS:
        raise ValueError(
            f"clip duration {probe.duration_seconds:.1f}s exceeds the 120s experiment limit"
        )


def _validate_offset(source_offset: float, clip: MediaProbe, original: MediaProbe) -> None:
    if not math.isfinite(source_offset) or source_offset < 0:
        raise ValueError("source offset must be a finite non-negative number")
    if not math.isfinite(original.duration_seconds) or original.duration_seconds <= 0:
        raise ValueError("original source has no positive finite duration")
    if source_offset + clip.duration_seconds > original.duration_seconds + 1e-6:
        raise ValueError(
            f"clip window [{source_offset}, {source_offset + clip.duration_seconds:.1f}] "
            f"exceeds original duration {original.duration_seconds:.1f}"
        )


def _validate_inline_budget(video: Path) -> int:
    """Exact encoded Base64 size must stay under the native inline cap."""
    encoded_bytes = 4 * math.ceil(video.stat().st_size / 3)
    if encoded_bytes >= MAX_INLINE_BASE64_BYTES:
        raise ValueError("clip exceeds the bounded inline Base64 video budget")
    return encoded_bytes


def _clip_mime_type(video: Path) -> str:
    guessed, _ = mimetypes.guess_type(video.name)
    return guessed or "application/octet-stream"


def _code_hashes() -> dict[str, str]:
    """SHA-256 of this script and every actual src/vidsnap module file."""
    hashes: dict[str, str] = {
        "scripts/native_video_review.py": sha256_file(Path(__file__).resolve())
    }
    src_root = REPO_ROOT / "src" / "vidsnap"
    for module_file in sorted(src_root.rglob("*.py")):
        key = module_file.relative_to(src_root).as_posix()
        hashes[key] = sha256_file(module_file)
    return hashes


async def validate_only(
    *,
    video: Path,
    original_source: Path,
    source_offset: float,
    output: Path,
    whisper_executable: Path,
    whisper_model: Path,
    media: FFmpegPort,
    forbidden_roots: tuple[Path, ...] | None = None,
) -> dict[str, Any]:
    """Probe and validate inputs; no model/ASR inference, no output writes."""
    roots = forbidden_roots if forbidden_roots is not None else default_forbidden_roots()
    ensure_output_dir(output, forbidden_roots=roots)
    _validate_whisper_dependencies(whisper_executable, whisper_model)
    clip_probe = await media.probe(video)
    original_probe = await media.probe(original_source)
    _validate_clip_probe(clip_probe)
    _validate_offset(source_offset, clip_probe, original_probe)
    base64_bytes = _validate_inline_budget(video)
    return {
        "mode": "validate-only",
        "clip_sha256": sha256_file(video),
        "original_sha256": sha256_file(original_source),
        "source_offset": source_offset,
        "task_hash": task_hash(),
        "clip": {
            "duration_seconds": clip_probe.duration_seconds,
            "fps": clip_probe.fps,
            "width": clip_probe.width,
            "height": clip_probe.height,
            "has_audio": clip_probe.has_audio,
            "mime_type": _clip_mime_type(video),
            "base64_bytes": base64_bytes,
        },
        "original": {
            "duration_seconds": original_probe.duration_seconds,
            "has_audio": original_probe.has_audio,
        },
    }


def usage_summary(usage: ProviderUsage) -> dict[str, Any]:
    """Project provider counters; unreported token values stay None."""
    return {
        "model_calls": usage.model_calls,
        "input_bytes": usage.input_bytes,
        "input_tokens": usage.input_tokens if usage.reported else None,
        "output_tokens": usage.output_tokens if usage.reported else None,
        "reported": usage.reported,
    }


def _runtime_configuration(
    *,
    clip_sha256: str,
    original_sha256: str,
    source_offset: float,
    budgets: dict[str, int],
    tools: list[str],
    frames_budget: str | None,
    identity: Any,
    code_hashes: dict[str, str],
    controls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Allowlisted runtime/provenance payload recorded before any execution."""
    config: dict[str, Any] = {
        "api_version": "vidsnap.review-config/v1",
        "clip_sha256": clip_sha256,
        "original_sha256": original_sha256,
        "source_offset": source_offset,
        "task_hash": task_hash(),
        "registered_tools": list(tools),
        "budgets": dict(budgets),
        "provider": {
            "id": identity.id,
            "model": identity.model,
            "base_url": identity.base_url,
        },
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "platform": sys.platform,
        "code_version": vidsnap.__version__,
        "code_hashes": dict(code_hashes),
    }
    if frames_budget is not None:
        config["frames_budget"] = frames_budget
    if controls is not None:
        config["controls"] = dict(controls)
    return config


def _record_configuration(bundle: RunBundle, config: dict[str, Any]) -> None:
    bundle.append_event(
        "runtime.configuration",
        config,
        event_id=uuid.uuid4().hex,
        event_type="runtime.configuration",
        status="completed",
    )


def _route_loop_spec(budgets: dict[str, int]) -> LoopSpec:
    return LoopSpec(
        budgets=LoopBudgets(
            max_iterations=1,
            max_model_calls=budgets["max_model_calls"],
            max_tool_calls=budgets["max_tool_calls"],
            max_evidence_frames=budgets["max_evidence_frames"],
            max_wall_seconds=budgets["max_wall_seconds"],
        )
    )


FAIL_FAST_CONTROLS: dict[str, str] = {
    "policy": "FailFastAgenticPolicy",
    "format_repair": "disabled",
    "verifier_repair": "disabled",
    "pre_execution_frame_cap": "enabled",
}


class FailFastAgenticPolicy:
    """Experimental opt-in agentic loop without any repair round.

    Same real-kernel decision loop as the public default policy — the model
    still chooses transcribe_audio/sample_evidence calls and their order —
    but the first AgentDecisionFormatError propagates to the kernel (which
    records FAILED) and the first failed final verification stops at PARTIAL
    instead of triggering a repair round. The public default policy in
    src/vidsnap is unchanged; this class exists only for this experiment.
    """

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        context: RunContext[Any, Any],
        kernel: HarnessKernel[Any, Any],
    ) -> None:
        await kernel.run_probe(context)
        while context.terminal_state is None:
            response = await kernel.request_agent_decision(context)
            decision = response.decision
            if decision.kind == "tool_calls":
                for call in decision.calls:
                    if call.name == "sample_evidence":
                        self._enforce_frame_cap(kernel, context, call.arguments)
                    await kernel.run_tool(context, call.name, call.arguments)
                continue
            kernel.accept_agent_final(context, decision)
            verification = kernel.verify(context)
            context.terminal_state = (
                TerminalState.SUCCEEDED if verification.passed else TerminalState.PARTIAL
            )
            return

    def _enforce_frame_cap(
        self,
        kernel: HarnessKernel[Any, Any],
        context: RunContext[Any, Any],
        arguments: Mapping[str, JsonValue],
    ) -> None:
        """Refuse an over-budget sample before any frame is extracted."""
        plugin = self._registry.tool_by_name("sample_evidence")
        validated = plugin.input_model.model_validate(dict(arguments))
        remaining = kernel.remaining_frame_budget(context)
        if validated.max_frames > remaining:
            raise BudgetExceeded(
                f"sample_evidence requested {validated.max_frames} frames "
                f"with {remaining} remaining"
            )


class _TracedTranscriber(TranscriptionPort):
    """Time one real local-ASR call on the run's own recorder timeline."""

    def __init__(self, inner: TranscriptionPort, trace: TraceRecorder) -> None:
        self._inner = inner
        self._trace = trace

    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/wav"
    ) -> TranscriptionResponse:
        span = self._trace.start(
            "local.asr",
            phase="transcribe_audio",
            payload={"audio_bytes": len(audio_bytes)},
        )
        try:
            response = await self._inner.transcribe(audio_bytes, mime_type=mime_type)
        except BaseException:
            self._trace.finish(span, status="failed")
            raise
        self._trace.finish(span, status="completed", usage=response.usage)
        return response


def _load_events(bundle_path: Path) -> list[dict[str, Any]]:
    events_file = bundle_path / "events.jsonl"
    if not events_file.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in events_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _load_bundle_evidence(bundle_path: Path) -> list[dict[str, Any]]:
    evidence_dir = bundle_path / "evidence"
    if not evidence_dir.is_dir():
        return []
    items: list[dict[str, Any]] = []
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


def _aggregate_usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate remote model-request usage; unknown counters stay None."""
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
            for key in ("input_tokens", "output_tokens"):
                value = usage.get(key)
                if isinstance(value, int):
                    if key == "input_tokens":
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


def _run_latency_ms(events: list[dict[str, Any]]) -> int | None:
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


def _local_asr_summary(executions: list[LocalWhisperExecution]) -> dict[str, Any]:
    records = [asdict(execution) for execution in executions]
    for record in records:
        record["model_path"] = Path(record["model_path"]).name
    return {
        "attempts": sum(1 for r in records if r["attempted"]),
        "calls": sum(1 for r in records if r["started"]),
        "completed": sum(1 for r in records if r["status"] == "completed"),
        "returncode_unknown": sum(1 for r in records if r["returncode"] is None),
        "audio_seconds": sum(r["audio_seconds"] for r in records) if records else 0.0,
        "audio_bytes": sum(r["audio_bytes"] for r in records) if records else 0,
        "duration_seconds": sum(r["duration_seconds"] for r in records) if records else 0.0,
        "executions": records,
    }


def _harness_section(
    result: KernelRunResult[Any],
    events: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    executions: list[LocalWhisperExecution],
) -> dict[str, Any]:
    frames = sum(1 for item in evidence if item.get("modality") == "frame")
    section: dict[str, Any] = {
        "run_path": Path(result.run_path).name,
        "terminal_state": result.terminal_state.value,
        "usage": _aggregate_usage(events),
        "events": events,
        "evidence": evidence,
        "frames": frames,
        "latency_ms": _run_latency_ms(events),
        "local_asr": _local_asr_summary(executions),
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


class _NativeNotes(StrictModel):
    """Validated text-only notes persisted inside the native bundle."""

    text: str


def _request_sent(category: str, attempts: int) -> bool | None:
    """Whether the provider demonstrably received the request; None = unknown."""
    if attempts == 0:
        return False
    if category in ("http_error", "stream_error"):
        return True
    return None


def _failed_usage(attempts: int, request_bytes: int) -> dict[str, Any]:
    return {
        "model_calls": attempts,
        "input_bytes": request_bytes,
        "input_tokens": None,
        "output_tokens": None,
        "reported": False,
    }


def _unknown_usage() -> dict[str, Any]:
    """Unobserved counters stay None; zero would fabricate measurement."""
    return {
        "model_calls": None,
        "input_bytes": None,
        "input_tokens": None,
        "output_tokens": None,
        "reported": False,
    }


def _reported_error_usage(error: NativeVideoError) -> ProviderUsage | None:
    """Complete provider-reported usage captured before the failure, if any."""
    usage = getattr(error, "usage", None)
    if isinstance(usage, ProviderUsage) and usage.reported:
        return usage
    return None


def _export_trace_safely(section: dict[str, Any], source: Path, output: Path) -> None:
    """Export one trace; failure is recorded, never erases the real outcome."""
    try:
        export_trace(source, output)
    except Exception as error:
        section["trace_export_error"] = type(error).__name__
    else:
        section["trace"] = output.name


def _run_terminal_latency_ms(bundle: RunBundle) -> int | None:
    for event in reversed(_load_events(bundle.path)):
        if event.get("event_type") in ("run.completed", "run.failed"):
            duration = event.get("duration_ms")
            return duration if isinstance(duration, int) else None
    return None


async def _run_native_route(
    *,
    video: Path,
    clip_probe: MediaProbe,
    clip_sha: str,
    output_dir: Path,
    native_client: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    """One traced native request in its own real bundle; failure is preserved."""
    bundle = RunBundle.create(
        output_dir / "native",
        loop_spec=_route_loop_spec(NATIVE_BUDGETS),
        provider_url=native_client.identity.base_url,
        provider_identity=native_client.identity,
    )
    _record_configuration(bundle, config)
    trace = TraceRecorder(bundle)
    run_span = trace.start(
        "run",
        phase="run",
        payload={"goal": COMMON_TASK, "source_sha256": clip_sha, "route": "native"},
    )
    span = trace.start(
        "model.request",
        phase="native_analyze",
        payload={"task_hash": task_hash(), "model": native_client.identity.model},
    )
    section: dict[str, Any] = {
        "frames": None,  # native internal frames are unknown, never invented
        "input_mode": "native_video",
        "has_audio": clip_probe.has_audio,
    }
    try:
        clip = NativeClip(
            path=video,
            mime_type=_clip_mime_type(video),
            duration_seconds=clip_probe.duration_seconds,
            sha256=clip_sha,
        )
        result = await native_client.analyze_clip(clip, task=COMMON_TASK)
    except NativeVideoError as error:
        reported_usage = _reported_error_usage(error)
        failed_usage = (
            reported_usage
            if reported_usage is not None
            else (
                ProviderUsage(
                    model_calls=error.attempts, input_bytes=error.request_bytes, reported=False
                )
                if error.attempts > 0
                else None
            )
        )
        trace.finish(
            span,
            status="failed",
            payload={"category": error.category, "http_status": error.http_status},
            usage=failed_usage,
        )
        trace.finish(
            run_span, status="failed", payload={"terminal_state": TerminalState.FAILED.value}
        )
        bundle.finalize(TerminalState.FAILED)
        section.update(
            {
                "status": "failed",
                "latency_ms": _run_terminal_latency_ms(bundle),
                "usage": (
                    usage_summary(reported_usage)
                    if reported_usage is not None
                    else _failed_usage(error.attempts, error.request_bytes)
                ),
                "failure": {
                    "category": error.category,
                    "http_status": error.http_status,
                    "attempts": error.attempts,
                    "request_sent": _request_sent(error.category, error.attempts),
                    "request_bytes": error.request_bytes,
                },
            }
        )
        _export_trace_safely(section, bundle.path, output_dir / "native-trace.html")
        return section
    except Exception as error:
        trace.finish(span, status="failed", payload={"category": "unexpected_error"})
        trace.finish(
            run_span, status="failed", payload={"terminal_state": TerminalState.FAILED.value}
        )
        bundle.finalize(TerminalState.FAILED)
        section.update(
            {
                "status": "failed",
                "latency_ms": _run_terminal_latency_ms(bundle),
                "usage": _unknown_usage(),
                "failure": {
                    "category": "unexpected_error",
                    "failure_class": type(error).__name__,
                    "request_sent": None,
                },
            }
        )
        _export_trace_safely(section, bundle.path, output_dir / "native-trace.html")
        return section
    trace.finish(span, status="completed", usage=result.usage)
    bundle.write_result(_NativeNotes(text=result.text))
    trace.finish(
        run_span, status="completed", payload={"terminal_state": TerminalState.SUCCEEDED.value}
    )
    bundle.finalize(TerminalState.SUCCEEDED)
    section.update(
        {
            "status": "completed",
            "latency_ms": _run_terminal_latency_ms(bundle),
            "text": result.text,
            "usage": usage_summary(result.usage),
            "request_bytes": result.request_bytes,
            "identity": asdict(result.identity),
        }
    )
    _export_trace_safely(section, bundle.path, output_dir / "native-trace.html")
    return section


async def _run_harness_route(
    *,
    video: Path,
    clip_sha: str,
    output_dir: Path,
    harness_client: Any,
    media: FFmpegPort,
    config: dict[str, Any],
    transcriber: LocalWhisperTranscriber,
    executions: list[LocalWhisperExecution],
) -> dict[str, Any]:
    """The bounded agentic Harness route on the real kernel and tools."""
    bundle = RunBundle.create(
        output_dir / "harness",
        loop_spec=_route_loop_spec(HARNESS_BUDGETS),
        provider_url=harness_client.identity.base_url,
        provider_identity=harness_client.identity,
    )
    _record_configuration(bundle, config)
    policy = HarnessPolicy(
        tool_mode="agentic",
        max_model_calls=HARNESS_BUDGETS["max_model_calls"],
        max_tool_calls=HARNESS_BUDGETS["max_tool_calls"],
        max_evidence_frames=HARNESS_BUDGETS["max_evidence_frames"],
        max_wall_seconds=HARNESS_BUDGETS["max_wall_seconds"],
    )
    registry = default_plugin_registry()
    kernel = HarnessKernel(policy=FailFastAgenticPolicy(registry), registry=registry)
    context: RunContext[Any, Any] = RunContext(
        source=VideoSource(path=video, sha256=clip_sha),
        policy=policy,
        bundle=bundle,
        task_adapter=VideoAnalysisTaskAdapter(VideoGoal(objective=COMMON_TASK)),
        task_model=harness_client,
        media=media,
        sampler=media.sampler,
        result_writer=bundle.write_result,
        agent_model=harness_client,
    )
    context.recognizer = _TracedTranscriber(transcriber, context.trace)
    result = await kernel.run(context)
    events = _load_events(bundle.path)
    evidence = _load_bundle_evidence(bundle.path)
    section = _harness_section(result, events, evidence, executions)
    _export_trace_safely(section, bundle.path, output_dir / "harness-trace.html")
    return section


async def run_review(
    *,
    video: Path,
    original_source: Path,
    source_offset: float,
    output_dir: Path,
    native_client: Any,
    harness_client: Any,
    media: FFmpegPort,
    whisper_runner: WhisperRunner | None = None,
    whisper_executable: Path,
    whisper_model: Path,
    forbidden_roots: tuple[Path, ...] | None = None,
) -> dict[str, Any]:
    """Run native first, then the bounded Harness route; native failure stops."""
    roots = forbidden_roots if forbidden_roots is not None else default_forbidden_roots()
    ensure_output_dir(output_dir, forbidden_roots=roots)
    _validate_whisper_dependencies(whisper_executable, whisper_model)
    clip_probe = await media.probe(video)
    original_probe = await media.probe(original_source)
    _validate_clip_probe(clip_probe)
    _validate_offset(source_offset, clip_probe, original_probe)
    _validate_inline_budget(video)

    output_dir.mkdir(parents=True, exist_ok=False)
    clip_sha = sha256_file(video)
    original_sha = sha256_file(original_source)
    clip_name = f"clip{video.suffix.lower()}" if video.suffix else "clip"
    shutil.copyfile(video, output_dir / clip_name)

    code_hashes = _code_hashes()
    report: dict[str, Any] = {
        "synthetic": False,
        "task": COMMON_TASK,
        "provenance": {
            "clip_sha256": clip_sha,
            "original_sha256": original_sha,
            "source_offset": source_offset,
            "clip_duration_seconds": clip_probe.duration_seconds,
            "original_duration_seconds": original_probe.duration_seconds,
            "task_hash": task_hash(),
            "code_version": vidsnap.__version__,
            "code_hashes": code_hashes,
        },
        "runtime": {
            "platform": sys.platform,
            "python_version": ".".join(str(part) for part in sys.version_info[:3]),
            "harness_provider": asdict(harness_client.identity),
            "native_provider": asdict(native_client.identity),
            "registered_tools": list(REGISTERED_TOOLS),
        },
        "budgets": dict(HARNESS_BUDGETS),
        "native_budgets": dict(NATIVE_BUDGETS),
        "clip_file": clip_name,
        "routes": {},
    }
    routes: dict[str, Any] = report["routes"]

    native_config = _runtime_configuration(
        clip_sha256=clip_sha,
        original_sha256=original_sha,
        source_offset=source_offset,
        budgets=NATIVE_BUDGETS,
        tools=[],
        frames_budget="not_applicable",
        identity=native_client.identity,
        code_hashes=code_hashes,
    )
    routes["native"] = await _run_native_route(
        video=video,
        clip_probe=clip_probe,
        clip_sha=clip_sha,
        output_dir=output_dir,
        native_client=native_client,
        config=native_config,
    )
    report["review_completed"] = False
    _write_outputs(output_dir, report)  # checkpoint: native outcome is durable now
    if routes["native"]["status"] != "completed":
        return report
    if "trace_export_error" in routes["native"]:
        # Delivery failed even though the call succeeded; stop before Harness.
        return report

    executions: list[LocalWhisperExecution] = []
    transcriber = LocalWhisperTranscriber(
        executable=whisper_executable,
        model_path=whisper_model,
        runner=whisper_runner,
        observer=executions.append,
    )
    harness_config = _runtime_configuration(
        clip_sha256=clip_sha,
        original_sha256=original_sha,
        source_offset=source_offset,
        budgets=HARNESS_BUDGETS,
        tools=list(REGISTERED_TOOLS),
        frames_budget=None,
        identity=harness_client.identity,
        code_hashes=code_hashes,
        controls=FAIL_FAST_CONTROLS,
    )
    try:
        routes["harness"] = await _run_harness_route(
            video=video,
            clip_sha=clip_sha,
            output_dir=output_dir,
            harness_client=harness_client,
            media=media,
            config=harness_config,
            transcriber=transcriber,
            executions=executions,
        )
    except Exception as error:
        # Keep the native checkpoint; record only the safe failure class.
        routes["harness"] = {"status": "failed", "failure_class": type(error).__name__}
    harness = routes["harness"]
    report["review_completed"] = (
        harness.get("terminal_state") == TerminalState.SUCCEEDED.value
        and "trace_export_error" not in harness
    )
    _write_outputs(output_dir, report)
    return report


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _usage_cells(usage: dict[str, Any]) -> str:
    cells = []
    for key in ("model_calls", "input_bytes", "input_tokens", "output_tokens"):
        value = usage.get(key)
        cells.append(f"{_esc(key)}: {_esc(value) if value is not None else 'unknown'}")
    return " | ".join(cells)


def render_report(report: dict[str, Any]) -> str:
    """Render a self-contained, XSS-safe Chinese review page."""
    provenance = report.get("provenance", {})
    routes = report.get("routes", {})
    offset = provenance.get("source_offset", 0)
    clip_file = str(report.get("clip_file", "clip"))
    suffix = Path(clip_file).suffix.lower()

    if suffix in _BROWSER_PLAYABLE_SUFFIXES:
        media_html = (
            f'<video id="player" controls width="720"><source src="{_esc(clip_file)}"></video>'
        )
    else:
        media_html = (
            f"<p>片段为 {_esc(suffix or '?')} 格式，本页不假装转码；"
            f'请下载原文件复核：<a href="{_esc(clip_file)}" download="{_esc(clip_file)}">'
            f"{_esc(clip_file)}</a></p>"
        )

    blocks: list[str] = []
    native = routes.get("native")
    if native is not None:
        if native.get("status") == "failed":
            failure = native.get("failure", {})
            blocks.append(
                '<div class="route"><h3>Native 原生音画路线</h3>'
                f"<p>状态: 失败 | category: {_esc(failure.get('category'))}"
                f" | http_status: {_esc(failure.get('http_status'))}"
                f" | attempts: {_esc(failure.get('attempts'))}"
                f" | 请求已发出: {_esc(failure.get('request_sent'))}"
                f" | serialized request bytes: {_esc(failure.get('request_bytes'))}</p>"
                f"<p>Native 路线失败，已保留安全记录并停止；Harness 路线未运行。</p>"
                f'<p><a href="native-trace.html">实际 trace 导出</a></p></div>'
            )
        else:
            blocks.append(
                '<div class="route"><h3>Native 原生音画路线</h3>'
                f"<p>{_usage_cells(native.get('usage', {}))}"
                f" | request_bytes: {_esc(native.get('request_bytes'))}"
                f" | latency: {_esc(native.get('latency_ms'))}ms</p>"
                f"<pre>{_esc(native.get('text', ''))}</pre>"
                f'<p class="note">Native 内部帧数未知；其时间引用未经独立核验；'
                f"Native 不套 Harness 帧预算（合同最小值仅为占位）。</p>"
                f'<p><a href="native-trace.html">实际 trace 导出</a></p></div>'
            )
    harness = routes.get("harness")
    if harness is not None:
        if harness.get("status") == "failed":
            blocks.append(
                '<div class="route"><h3>Harness 有界代理路线</h3>'
                f"<p>状态: 失败 ({_esc(harness.get('failure_class', 'unknown'))})；"
                f"Native checkpoint 已保留。</p></div>"
            )
        else:
            blocks.append(_render_harness_block(harness, offset))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Native 音画对照评审</title>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
.route {{ margin-bottom: 1em; padding: 1em; background: #f9f9f9; }}
pre {{ white-space: pre-wrap; word-break: break-all; }}
.note {{ color: #555; }}
</style>
</head>
<body>
<h1>Native 音画 vs 有界 Harness 对照评审</h1>
<p class="note">两路线模型不同（qwen3.5-omni-plus 原生音画 vs qwen3.8-max + 本地Whisper），
仅整体方案对照，不构成 superiority 证据；Native 时间引用未经独立核验；本页不做质量结论。</p>
<p>clip sha256: {_esc(provenance.get("clip_sha256", ""))} |
original sha256: {_esc(provenance.get("original_sha256", ""))} |
offset: {_esc(provenance.get("source_offset", ""))}s |
task hash: {_esc(provenance.get("task_hash", ""))}</p>
{media_html}
{"".join(blocks)}
</body>
</html>"""


def _render_harness_block(harness: dict[str, Any], offset: object) -> str:
    event_items: list[str] = []
    for event in harness.get("events", []):
        duration = event.get("duration_ms")
        event_items.append(
            "<li>"
            f"#{_esc(event.get('sequence', '?'))} {_esc(event.get('event_type', ''))} "
            f"[{_esc(event.get('status', ''))}] "
            f"{_esc(duration) if duration is not None else 'unknown'}ms</li>"
        )
    local_asr = harness.get("local_asr", {})
    verification = harness.get("verification") or {}
    gates = verification.get("gates", {})
    gates_html = " ".join(f"{_esc(gate)}={'✓' if ok else '✗'}" for gate, ok in gates.items())
    output = harness.get("output") or {}
    claim_items = []
    evidence_starts = {
        str(item.get("id", "")): item.get("start_seconds") for item in harness.get("evidence", [])
    }
    for claim in output.get("claims", []):
        refs = []
        for ref in claim.get("evidence", []):
            ref_id = str(ref.get("evidence_id", ""))
            start = evidence_starts.get(ref_id)
            if isinstance(start, (int, float)) and isinstance(offset, (int, float)):
                refs.append(f"{_esc(ref_id)} (原片 {_esc(f'{start + offset:.0f}')}s)")
            else:
                refs.append(f"{_esc(ref_id)} (原片时间未知)")
        claim_items.append(f"<li>{_esc(claim.get('text', ''))} [{'; '.join(refs)}]</li>")
    asr_seconds = f"{local_asr.get('audio_seconds', 0.0):.2f}"
    asr_duration = f"{local_asr.get('duration_seconds', 0.0):.2f}"
    return (
        '<div class="route"><h3>Harness 有界代理路线</h3>'
        f"<p>terminal: {_esc(harness.get('terminal_state', 'unknown'))}"
        f" | {_usage_cells(harness.get('usage', {}))}"
        f" | frames: {_esc(harness.get('frames'))}"
        f" | latency: {_esc(harness.get('latency_ms'))}ms</p>"
        f"<p>本地ASR: 调用 {_esc(local_asr.get('calls', 0))} 次"
        f" | 音频 {_esc(asr_seconds)}s"
        f" | {_esc(local_asr.get('audio_bytes', 0))} bytes"
        f" | 耗时 {_esc(asr_duration)}s</p>"
        f"<p>verifier gates: {gates_html}</p>"
        f"<p><strong>summary</strong>: {_esc(output.get('summary', ''))}</p>"
        f"<ul>{''.join(claim_items)}</ul>"
        f'<p><a href="harness-trace.html">实际 trace 导出</a></p>'
        f"<ol>{''.join(event_items)}</ol></div>"
    )


def _write_outputs(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "index.html").write_text(render_report(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Native video two-route review")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--original-source", required=True, type=Path)
    parser.add_argument("--source-offset", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--whisper-executable", required=True, type=Path)
    parser.add_argument("--whisper-model", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.validate_only:
            summary = asyncio.run(
                validate_only(
                    video=args.video,
                    original_source=args.original_source,
                    source_offset=args.source_offset,
                    output=args.output,
                    whisper_executable=args.whisper_executable,
                    whisper_model=args.whisper_model,
                    media=FFmpegMediaPort(),
                )
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        harness_key = os.environ.get("VIDSNAP_QWEN_API_KEY")
        native_key = os.environ.get("VIDSNAP_MODEL_STUDIO_UPLOAD_API_KEY")
        report = asyncio.run(
            run_review(
                video=args.video,
                original_source=args.original_source,
                source_offset=args.source_offset,
                output_dir=args.output,
                native_client=NativeVideoClient(api_key=native_key),
                harness_client=QwenProvider(api_key=harness_key),
                media=FFmpegMediaPort(),
                whisper_executable=args.whisper_executable,
                whisper_model=args.whisper_model,
            )
        )
        print(f"review complete: {args.output}")
        return 0 if report.get("review_completed") else 1
    except ValueError as exc:
        print(f"review validation failed: {exc.__class__.__name__}", file=sys.stderr)
        return 1
    except Exception:
        print("review failed with an unexpected error", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
