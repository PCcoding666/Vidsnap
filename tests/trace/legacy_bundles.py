"""Write RunBundles in the exact shapes the v0.1.0 kernel produced.

The v0.1.0 kernel wrote ``run.started`` with only ``{"policy": ...}``,
``tool.call.started`` with only ``{"name": ...}``, failed ``model.request``
events with an empty payload and no usage, and ``run.<status>`` with only
``{"terminal_state": ...}``. These helpers synthesize such a bundle at test time
so compatibility is proven without committing any recorded RunBundle.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

V010_RUN_ID = "11111111-2222-4333-8444-555555555555"


def _event(sequence: int, **fields: object) -> dict[str, object]:
    event: dict[str, object] = {
        "sequence": sequence,
        "occurred_at": f"2026-10-05T00:00:{sequence:02d}Z",
        "payload": {},
    }
    event.update(fields)
    return event


def write_v010_failed_bundle(path: Path, *, provider_identity: bool = False) -> Path:
    """A finalized v0.1.0 FixedPolicy bundle whose model request failed."""
    path.mkdir(parents=True)
    (path / "evidence").mkdir()
    (path / "artifacts").mkdir()
    events = [
        _event(
            1,
            phase="run",
            event_id="e1",
            event_type="run.started",
            correlation_id="c-run",
            monotonic_offset_ms=0,
            status="started",
            payload={"policy": "FixedPolicy"},
        ),
        _event(
            2,
            phase="probe_media",
            event_id="e2",
            event_type="probe.started",
            correlation_id="c-probe",
            monotonic_offset_ms=1,
            status="started",
        ),
        _event(
            3,
            phase="probe_media",
            event_id="e3",
            event_type="probe.completed",
            correlation_id="c-probe",
            monotonic_offset_ms=5,
            status="completed",
            duration_ms=4,
            payload={
                "duration_seconds": 42.5,
                "fps": 24.0,
                "width": 320,
                "height": 240,
                "has_audio": True,
            },
        ),
        _event(
            4,
            phase="sample_evidence",
            event_id="e4",
            event_type="tool.call.started",
            correlation_id="c-tool",
            monotonic_offset_ms=6,
            status="started",
            payload={"name": "sample_evidence"},
        ),
        _event(
            5,
            phase="sample_evidence",
            event_id="e5",
            event_type="tool.call.completed",
            correlation_id="c-tool",
            monotonic_offset_ms=20,
            status="completed",
            duration_ms=14,
            payload={"name": "sample_evidence"},
            usage={
                "model_calls": 0,
                "tool_calls": 0,
                "evidence_frames": 0,
                "input_bytes": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "provider_reported": False,
            },
        ),
        _event(
            6,
            phase="budget",
            event_id="e6",
            event_type="budget.updated",
            status="completed",
            payload={"iterations": 1, "tool_calls": 1, "model_calls": 0, "evidence_frames": 2},
        ),
        _event(
            7,
            phase="synthesize_result",
            event_id="e7",
            event_type="model.request.started",
            correlation_id="c-model",
            monotonic_offset_ms=21,
            status="started",
            payload={"task": "VideoAnalysisTaskAdapter"},
        ),
        _event(
            8,
            phase="synthesize_result",
            event_id="e8",
            event_type="model.request.failed",
            correlation_id="c-model",
            monotonic_offset_ms=681,
            status="failed",
            duration_ms=660,
        ),
        _event(
            9,
            phase="budget",
            event_id="e9",
            event_type="budget.updated",
            status="completed",
            payload={"iterations": 1, "tool_calls": 1, "model_calls": 1, "evidence_frames": 2},
        ),
        _event(
            10,
            phase="terminal",
            event_id="e10",
            event_type="phase.completed",
            status="completed",
            payload={"terminal_state": "FAILED", "reason": "unexpected kernel error"},
        ),
        _event(
            11,
            phase="run",
            event_id="e11",
            event_type="run.failed",
            correlation_id="c-run",
            monotonic_offset_ms=690,
            status="failed",
            duration_ms=690,
            payload={"terminal_state": "FAILED"},
        ),
    ]
    ledger = "".join(
        json.dumps(event, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        for event in events
    )
    (path / "events.jsonl").write_text(ledger, encoding="utf-8")
    provider: dict[str, object] = {"base_url": "https://host.invalid/compatible-mode/v1"}
    if provider_identity:
        provider = {"id": "acme", "model": "acme-large", **provider}
    manifest = {
        "api_version": "vidsnap.run/v1",
        "trace_schema": "vidsnap.trace/v1",
        "run_id": V010_RUN_ID,
        "created_at": "2026-10-05T00:00:00Z",
        "finalized_at": "2026-10-05T00:00:11Z",
        "terminal_state": "FAILED",
        "code_version": "0.1.0",
        "loop_spec": {
            "api_version": "vidsnap.loop/v1",
            "id": "grounded-video-understanding",
            "sha256": "0" * 64,
        },
        "resources": {
            "max_evidence_frames": 96,
            "max_iterations": 3,
            "max_model_calls": 12,
            "max_tool_calls": 6,
            "max_wall_seconds": 900,
        },
        "provider": provider,
        "verification": {},
        "files": {
            "events.jsonl": {
                "sha256": hashlib.sha256(ledger.encode("utf-8")).hexdigest(),
                "bytes": len(ledger.encode("utf-8")),
            }
        },
    }
    (path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
