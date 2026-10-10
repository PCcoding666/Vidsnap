"""Per-stage metrics from a finished RunBundle, and where each missed key point was lost.

Stages of the harness pipeline: probe, ASR (``transcribe_audio``), sampling
(``sample_evidence``), synthesis (the model request), verifier and repair. The
evidence files show exactly what the model saw, so a missed key point is
attributed to the first stage that dropped it. Native runs have no stages; only
their time split is reported.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import JsonValue, ValidationError

from vidsnap.contracts import Evidence
from vidsnap.eval.graders import moment_hits
from vidsnap.eval.suite import EvalItem, KeyPoint
from vidsnap.eval.text import error_rate, matches, normalize
from vidsnap.loop.events import RunEvent

_WINDOW_TOLERANCE = 5.0
_AUDIO_SUFFIXES = frozenset({".wav", ".mp3", ".aac"})
LOSS_STAGES = (
    "lost_at_asr",
    "lost_at_sampling",
    "lost_at_perception",
    "lost_at_synthesis",
    "unattributed",
)


def read_events(bundle: Path) -> list[RunEvent]:
    events: list[RunEvent] = []
    try:
        lines = (bundle / "events.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return events
    for line in lines:
        if not line.strip():
            continue
        try:
            events.append(RunEvent.model_validate_json(line))
        except ValidationError:
            continue
    return events


def read_evidence(bundle: Path) -> list[Evidence]:
    items: list[Evidence] = []
    directory = bundle / "evidence"
    if not directory.is_dir():
        return items
    for path in sorted(directory.glob("*.json")):
        try:
            items.append(Evidence.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, ValidationError):
            continue
    return items


def stage_timings(events: list[RunEvent]) -> dict[str, JsonValue]:
    """Milliseconds per stage from completed or failed spans."""
    timings: Counter[str] = Counter()
    run_ms: int | None = None
    for event in events:
        event_type = event.event_type or ""
        if event.duration_ms is None or event.status not in ("completed", "failed", "blocked"):
            continue
        if event_type.startswith("run."):
            run_ms = event.duration_ms
        elif event_type.startswith("probe."):
            timings["probe"] += event.duration_ms
        elif event_type.startswith("tool.call."):
            timings[f"tool:{event.phase}"] += event.duration_ms
        elif event_type.startswith("model.request."):
            timings[f"model:{event.phase}"] += event.duration_ms
    result: dict[str, JsonValue] = {key: value for key, value in sorted(timings.items())}
    result["run"] = run_ms
    return result


def _point_in_frames(point: KeyPoint, frame_times: list[float]) -> bool | None:
    if point.window is None:
        return None
    start, end = point.window
    return any(start - _WINDOW_TOLERANCE <= time <= end + _WINDOW_TOLERANCE for time in frame_times)


def loss_stage(
    point: KeyPoint,
    *,
    transcript_text: str | None,
    frame_times: list[float],
) -> str:
    """The first harness stage that dropped one missed key point."""
    in_transcript = (
        matches(normalize(transcript_text), point.match) if transcript_text is not None else False
    )
    in_frames = _point_in_frames(point, frame_times)
    if point.modality == "speech":
        return "lost_at_synthesis" if in_transcript else "lost_at_asr"
    if point.modality == "visual":
        if in_frames is None:
            return "unattributed"
        return "lost_at_synthesis" if in_frames else "lost_at_sampling"
    if in_transcript or in_frames:
        return "lost_at_synthesis"
    if in_frames is None:
        return "lost_at_asr" if transcript_text is not None else "unattributed"
    return "lost_at_perception"


def stage_metrics(
    bundle: Path, item: EvalItem, grade: dict[str, JsonValue], *, harness: bool
) -> dict[str, JsonValue]:
    """Per-stage metrics for one run; harness-only fields are omitted for native runs."""
    events = read_events(bundle)
    metrics: dict[str, JsonValue] = {"timings_ms": stage_timings(events)}
    for event in events:
        if event.event_type == "probe.completed":
            metrics["frame_width"] = event.payload.get("width")
            metrics["frame_height"] = event.payload.get("height")
            break
    metrics["model_request_bytes"] = sum(
        event.usage.input_bytes
        for event in events
        if (event.event_type or "") in ("model.request.completed", "model.request.failed")
        and event.usage is not None
    )
    audio = [
        path.stat().st_size
        for path in (bundle / "artifacts").rglob("*")
        if path.is_file() and path.suffix in _AUDIO_SUFFIXES
    ]
    recognizer = _speech_recognizer_id(events)
    uploaded = bool(audio) and recognizer is not None and recognizer not in ("oracle", "mock")
    # One request carries one file, so the Base64 inflation applies per file.
    metrics["asr_upload_bytes"] = sum(4 * ((size + 2) // 3) for size in audio) if uploaded else 0
    if not harness:
        return metrics
    evidence = read_evidence(bundle)
    transcripts = [entry for entry in evidence if entry.modality == "transcript"]
    frames = sorted({entry.start_seconds for entry in evidence if entry.modality == "frame"})
    transcript_text = (
        "\n".join(entry.content or "" for entry in transcripts) if transcripts else None
    )
    reference = item.reference
    metrics["frames_sampled"] = len(frames)
    metrics["transcript_items"] = len(transcripts)
    metrics["transcript_max_span_seconds"] = (
        max(entry.end_seconds - entry.start_seconds for entry in transcripts)
        if transcripts
        else None
    )
    if reference.transcript is not None and reference.transcript.segments:
        if transcript_text is not None:
            rate, truncated = error_rate(
                transcript_text, reference.transcript.text(), reference.transcript.language
            )
            key = "asr_cer" if reference.transcript.language == "zh" else "asr_wer"
            metrics[key] = rate
            metrics["asr_alignment_truncated"] = truncated
        else:
            metrics["asr_cer" if reference.transcript.language == "zh" else "asr_wer"] = None
    if reference.key_moments:
        hits = moment_hits(reference.key_moments, [(time, time) for time in frames])
        metrics["frame_moment_recall"] = round(
            sum(1 for hit in hits.values() if hit) / len(hits), 4
        )
    speech_points = [point for point in reference.key_points if point.modality != "visual"]
    if speech_points and transcript_text is not None:
        normalized = normalize(transcript_text)
        present = [point for point in speech_points if matches(normalized, point.match)]
        metrics["evidence_key_point_coverage"] = round(len(present) / len(speech_points), 4)
    missed_ids = grade.get("missed_key_points")
    losses: Counter[str] = Counter()
    per_point: dict[str, JsonValue] = {}
    if isinstance(missed_ids, list):
        by_id = {point.id: point for point in reference.key_points}
        for point_id in missed_ids:
            point = by_id.get(str(point_id))
            if point is None:
                continue
            stage = loss_stage(point, transcript_text=transcript_text, frame_times=list(frames))
            losses[stage] += 1
            per_point[point.id] = stage
    metrics["losses"] = {stage: losses.get(stage, 0) for stage in LOSS_STAGES}
    metrics["loss_by_point"] = per_point
    metrics.update(_verifier_metrics(events))
    return metrics


def _speech_recognizer_id(events: list[RunEvent]) -> str | None:
    for event in events:
        if event.event_type == "run.started":
            recognizer = event.payload.get("speech_recognizer")
            if isinstance(recognizer, dict) and isinstance(recognizer.get("id"), str):
                return str(recognizer["id"])
            return None
    return None


def _verifier_metrics(events: list[RunEvent]) -> dict[str, JsonValue]:
    verifications = [event for event in events if event.event_type == "verifier.completed"]
    repairs = sum(1 for event in events if event.event_type == "repair.requested")
    first: Any = verifications[0].payload if verifications else {}
    last: Any = verifications[-1].payload if verifications else {}
    return {
        "verifier_runs": len(verifications),
        "verifier_first_passed": first.get("passed") if verifications else None,
        "verifier_last_passed": last.get("passed") if verifications else None,
        "verifier_failed_gates": list(last.get("failed_gates") or []) if verifications else [],
        "repair_rounds": repairs,
    }
