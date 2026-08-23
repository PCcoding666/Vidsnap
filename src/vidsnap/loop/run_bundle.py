"""Filesystem-backed, secret-redacted audit bundles for one harness run."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import JsonValue

from vidsnap import __version__
from vidsnap.contracts import Evidence, LoopSpec, TerminalState
from vidsnap.contracts.models import StrictModel
from vidsnap.loop.events import EventStatus, EventUsage, RunEvent

_SENSITIVE_KEY_PARTS = ("api_key", "authorization", "credential", "password", "secret", "token")
_SAFE_USAGE_COUNTERS = {
    "completion_tokens",
    "input_tokens",
    "output_tokens",
    "prompt_tokens",
    "total_tokens",
}


def redact_provider_url(provider_url: str) -> str:
    """Return a provider URL without credentials, query values, or fragments."""
    split = urlsplit(provider_url)
    if not split.scheme or not split.hostname:
        return ""

    host = split.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if split.port is not None:
        host = f"{host}:{split.port}"
    return urlunsplit((split.scheme, host, split.path, "", ""))


def _redact_payload(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: (
                item
                if key.lower() in _SAFE_USAGE_COUNTERS
                and isinstance(item, int)
                and not isinstance(item, bool)
                and item >= 0
                else "***REDACTED***"
            )
            if any(part in key.lower() for part in _SENSITIVE_KEY_PARTS)
            else _redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json_write(path: Path, data: object) -> None:
    """Write JSON via a same-directory temporary file and atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        Path(temporary_path).unlink(missing_ok=True)
        raise


def _file_digest(path: Path) -> dict[str, int | str]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}


class RunBundle:
    """An append-only audit record for exactly one local harness invocation."""

    def __init__(self, path: Path, manifest: dict[str, object]) -> None:
        self.path = path
        self._manifest = manifest
        self._event_sequence = 0
        self._finalized = False

    @classmethod
    def create(cls, path: Path, *, loop_spec: LoopSpec, provider_url: str) -> RunBundle:
        """Create the required bundle layout without embedding provider credentials."""
        path = path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        if any(path.iterdir()):
            raise FileExistsError(f"RunBundle directory must be empty: {path}")

        (path / "evidence").mkdir()
        (path / "artifacts").mkdir()
        (path / "events.jsonl").touch()
        manifest: dict[str, object] = {
            "api_version": "vidsnap.run/v1",
            "trace_schema": "vidsnap.trace/v1",
            "run_id": str(uuid.uuid4()),
            "created_at": _utc_now(),
            "finalized_at": None,
            "terminal_state": None,
            "code_version": __version__,
            "loop_spec": {
                "api_version": loop_spec.api_version,
                "id": loop_spec.id,
                "sha256": loop_spec.digest(),
            },
            "resources": loop_spec.budgets.model_dump(mode="json"),
            "provider": {"base_url": redact_provider_url(provider_url)},
            "verification": {},
            "files": {},
        }
        bundle = cls(path, manifest)
        bundle._write_manifest()
        return bundle

    def append_event(
        self,
        phase: str,
        payload: dict[str, JsonValue] | None = None,
        *,
        event_id: str | None = None,
        event_type: str | None = None,
        turn: int | None = None,
        step: int | None = None,
        parent_event_id: str | None = None,
        correlation_id: str | None = None,
        monotonic_offset_ms: int | None = None,
        status: EventStatus | None = None,
        usage: EventUsage | None = None,
        duration_ms: int | None = None,
    ) -> RunEvent:
        """Append a redacted JSONL event and return its typed representation."""
        self._ensure_open()
        self._event_sequence += 1
        redacted_payload = _redact_payload(payload or {})
        assert isinstance(redacted_payload, dict)
        event = RunEvent(
            sequence=self._event_sequence,
            phase=phase,
            payload=redacted_payload,
            event_id=event_id,
            event_type=event_type,
            turn=turn,
            step=step,
            parent_event_id=parent_event_id,
            correlation_id=correlation_id,
            monotonic_offset_ms=monotonic_offset_ms,
            status=status,
            usage=usage,
            duration_ms=duration_ms,
        )
        with (self.path / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(event.to_json())
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event

    def write_evidence(self, evidence: Evidence) -> Path:
        """Write one structured evidence item beneath the bundle evidence directory."""
        self._ensure_open()
        if Path(evidence.id).name != evidence.id:
            raise ValueError("evidence id must be a filename, not a path")
        output_path = self.path / "evidence" / f"{evidence.id}.json"
        _atomic_json_write(output_path, evidence.model_dump(mode="json"))
        return output_path

    def write_result(self, result: StrictModel) -> Path:
        """Atomically write the validated structured result."""
        self._ensure_open()
        output_path = self.path / "result.json"
        _atomic_json_write(output_path, result.model_dump(mode="json"))
        return output_path

    def finalize(self, reason: TerminalState | str) -> None:
        """Record a valid terminal state and content hashes exactly once."""
        self._ensure_open()
        terminal_state = TerminalState(reason)
        self._manifest["terminal_state"] = terminal_state.value
        self._manifest["finalized_at"] = _utc_now()
        self._manifest["files"] = self._collect_file_hashes()
        self._write_manifest()
        self._finalized = True

    def _collect_file_hashes(self) -> dict[str, dict[str, int | str]]:
        file_hashes: dict[str, dict[str, int | str]] = {}
        for candidate in sorted(self.path.rglob("*")):
            if candidate.is_file() and candidate.name != "manifest.json":
                relative_path = candidate.relative_to(self.path).as_posix()
                file_hashes[relative_path] = _file_digest(candidate)
        return file_hashes

    def _write_manifest(self) -> None:
        _atomic_json_write(self.path / "manifest.json", self._manifest)

    def _ensure_open(self) -> None:
        if self._finalized:
            raise RuntimeError("RunBundle is already finalized")


@contextmanager
def temporary_run_bundle(
    *,
    parent: Path | None = None,
    loop_spec: LoopSpec,
    provider_url: str,
) -> Iterator[RunBundle]:
    """Yield a temporary RunBundle and remove every artifact when it closes."""
    parent_path = parent.resolve() if parent is not None else None
    temporary_path = Path(tempfile.mkdtemp(prefix="vidsnap-", dir=parent_path))
    try:
        yield RunBundle.create(temporary_path, loop_spec=loop_spec, provider_url=provider_url)
    finally:
        shutil.rmtree(temporary_path, ignore_errors=True)
