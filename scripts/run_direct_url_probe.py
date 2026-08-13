#!/usr/bin/env python3
"""Run one sanitized Direct URL transport compatibility probe."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from vidsnap.benchmark.formal import FormalCase
from vidsnap.benchmark.live import BenchmarkProviderConfig
from vidsnap.benchmark.manifest import REGISTERED_MANIFEST_SHA256
from vidsnap.benchmark.url_probe import (
    DIRECT_URL_PROBE_FPS,
    REGISTERED_PROBE_CASE_ID,
    REGISTERED_PROBE_SHA256,
    REGISTERED_PROBE_SOURCE_BYTES,
    DirectUrlProbeClient,
    DirectUrlProbeFailure,
    DirectUrlProbeResult,
    validate_probe_case,
)
from vidsnap.config import QWEN_MODEL
from vidsnap.providers.base import ProviderUnavailable

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class _ProbeClient(Protocol):
    async def run(self, case: FormalCase) -> DirectUrlProbeResult:
        """Return one sanitized compatibility result."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise ValueError("probe input cannot be read") from None
    return digest.hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _repository_roots() -> tuple[Path, ...]:
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError("cannot verify every git worktree for external output") from None
    roots = tuple(
        Path(line.removeprefix("worktree ")).resolve()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    )
    if not roots:
        raise ValueError("cannot verify every git worktree for external output")
    return roots


def _assert_external_output(output_dir: Path) -> None:
    if any(_is_within(output_dir, root) for root in _repository_roots()):
        raise ValueError("probe output directory must be outside every git worktree")


def _load_probe_case(
    manifest_path: Path,
    *,
    expected_manifest_sha256: str,
) -> FormalCase:
    if not manifest_path.is_absolute() or not manifest_path.is_file():
        raise ValueError("probe manifest must be an absolute readable file")
    if _sha256(manifest_path) != expected_manifest_sha256:
        raise ValueError("manifest does not match the committed pre-registration")
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise ValueError("probe manifest cannot be read") from None
    cases: list[FormalCase] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            cases.append(FormalCase.model_validate_json(line))
        except ValidationError:
            raise ValueError("probe manifest contains an invalid case") from None
    matches = [case for case in cases if case.case_id == REGISTERED_PROBE_CASE_ID]
    if len(matches) != 1:
        raise ValueError("manifest must contain exactly one registered probe case")
    case = matches[0]
    try:
        validate_probe_case(case)
    except DirectUrlProbeFailure:
        raise ValueError("registered probe case failed local validation") from None
    return case


def _validation_summary(manifest_sha256: str) -> dict[str, object]:
    return {
        "status": "VALIDATED",
        "case_id": REGISTERED_PROBE_CASE_ID,
        "model": QWEN_MODEL,
        "fps": DIRECT_URL_PROBE_FPS,
        "source_sha256": REGISTERED_PROBE_SHA256,
        "source_bytes": REGISTERED_PROBE_SOURCE_BYTES,
        "manifest_sha256": manifest_sha256,
    }


def _atomic_json_write(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


async def _execute_probe(
    case: FormalCase,
    *,
    output_dir: Path,
    client: _ProbeClient,
) -> tuple[DirectUrlProbeResult, Path]:
    output_dir.mkdir(parents=True, exist_ok=False)
    result = await client.run(case)
    report_path = output_dir / "report.json"
    _atomic_json_write(report_path, result.model_dump(mode="json"))
    return result, report_path


def _terminal_summary(result: DirectUrlProbeResult, report_path: Path) -> dict[str, object]:
    return {"status": result.status, "report_path": str(report_path)}


def _exit_code(result: DirectUrlProbeResult) -> int:
    return 0 if result.status == "PROBE_SUCCEEDED" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if not args.manifest.is_absolute() or not args.output_dir.is_absolute():
        parser.error("probe manifest and output directory must use absolute paths")
    output_dir = args.output_dir.resolve()
    try:
        _assert_external_output(output_dir)
        manifest_path = args.manifest.resolve()
        case = _load_probe_case(
            manifest_path,
            expected_manifest_sha256=REGISTERED_MANIFEST_SHA256["smoke"],
        )
    except ValueError as error:
        parser.error(str(error))
    manifest_sha256 = _sha256(manifest_path)
    if args.validate_only:
        print(json.dumps(_validation_summary(manifest_sha256), ensure_ascii=True, sort_keys=True))
        return
    try:
        config = BenchmarkProviderConfig.from_env()
    except (ProviderUnavailable, ValueError):
        parser.error("Hermes Qwen configuration is unavailable")
    result, report_path = asyncio.run(
        _execute_probe(
            case,
            output_dir=output_dir,
            client=DirectUrlProbeClient(config),
        )
    )
    print(json.dumps(_terminal_summary(result, report_path), ensure_ascii=True, sort_keys=True))
    raise SystemExit(_exit_code(result))


if __name__ == "__main__":
    main()
