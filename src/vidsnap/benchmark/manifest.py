"""Pre-registered public-case selection and external manifest preparation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vidsnap.benchmark.formal import EvidenceRequirement, FormalCase
from vidsnap.contracts import AcquisitionTool

VIDEO_MME_REVISION = "ead1408f75b618502df9a1d8e0950166bf0a2a0b"
MVBENCH_ANNOTATION_REVISION = "230a2d4fac8900333c61754641c7a13e069ac9c6"
MVBENCH_VIDEO_REVISION = "a776e554280b99b70f00cc3eacd69a65e0727efc"


@dataclass(frozen=True, slots=True)
class RegisteredCase:
    """One public case ID plus a human pre-registration of needed evidence."""

    case_id: str
    requirements: tuple[EvidenceRequirement, ...]


def _registered(
    case_id: str,
    *requirements: EvidenceRequirement,
) -> RegisteredCase:
    return RegisteredCase(case_id, requirements)


FORMAL_SELECTION: dict[Literal["Video-MME", "MVBench"], tuple[RegisteredCase, ...]] = {
    "Video-MME": (
        _registered("050-1", "visual", "temporal"),
        _registered("050-2", "visual", "temporal"),
        _registered("050-3", "speech"),
        _registered("119-1", "visual"),
        _registered("119-2", "visual"),
        _registered("119-3", "speech", "visual"),
        _registered("212-1", "visual", "temporal"),
        _registered("212-2", "visual"),
        _registered("212-3", "visual"),
        _registered("007-1", "visual"),
        _registered("007-2", "visual", "temporal"),
        _registered("007-3", "visual"),
        _registered("527-1", "visual", "temporal"),
        _registered("527-2", "visual"),
        _registered("527-3", "visual"),
        _registered("599-1", "visual"),
        _registered("599-2", "visual", "temporal"),
        _registered("599-3", "visual"),
        _registered("482-1", "speech", "visual"),
        _registered("482-2", "visual", "temporal"),
        _registered("482-3", "speech"),
        _registered("428-1", "speech"),
        _registered("428-2", "visual"),
        _registered("428-3", "speech", "visual"),
        _registered("673-1", "speech"),
        _registered("673-2", "speech", "temporal"),
        _registered("673-3", "speech"),
        _registered("634-1", "speech"),
        _registered("634-2", "speech", "temporal"),
        _registered("634-3", "speech"),
        _registered("743-1", "speech", "visual"),
        _registered("743-2", "visual", "temporal"),
        _registered("743-3", "visual", "temporal"),
        _registered("847-1", "visual"),
        _registered("847-2", "visual"),
        _registered("847-3", "visual", "temporal"),
    ),
    "MVBench": tuple(_registered(str(index), "visual", "temporal") for index in range(18)),
}

SMOKE_SELECTION: dict[Literal["Video-MME", "MVBench"], tuple[RegisteredCase, ...]] = {
    "Video-MME": (
        _registered("069-2", "visual"),
        _registered("395-2", "visual", "temporal"),
        _registered("419-1", "speech"),
        _registered("701-2", "speech", "temporal"),
    ),
    "MVBench": (
        _registered("18", "visual", "temporal"),
        _registered("19", "visual", "temporal"),
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe(path: Path) -> tuple[float, bool]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    duration = float(payload["format"]["duration"])
    has_audio = any(stream.get("codec_type") == "audio" for stream in payload["streams"])
    return duration, has_audio


def _actual_duration_stratum(duration: float) -> Literal["short", "medium", "long"]:
    if duration < 120:
        return "short"
    if duration < 1800:
        return "medium"
    return "long"


def _expected_tools(
    requirements: tuple[EvidenceRequirement, ...],
) -> tuple[AcquisitionTool, ...]:
    tools: list[AcquisitionTool] = []
    if "speech" in requirements:
        tools.append("transcribe_audio")
    if "visual" in requirements or "temporal" in requirements:
        tools.append("sample_evidence")
    return tuple(tools)


def _option_map(options: list[object]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for index, option in enumerate(options):
        if not isinstance(option, str):
            raise ValueError("benchmark option must be text")
        label = chr(ord("A") + index)
        prefix = f"{label}. "
        mapped[label] = option.removeprefix(prefix).strip()
    return mapped


def _load_video_mme_rows(root: Path) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    pages = sorted((root / "annotations" / "videomme-pages").glob("*.json"))
    if len(pages) != 27:
        raise ValueError("expected all 27 fixed-revision Video-MME pages")
    for page in pages:
        payload = json.loads(page.read_text(encoding="utf-8"))
        for wrapped in payload["rows"]:
            row = wrapped["row"]
            rows[str(row["question_id"])] = row
    if len(rows) != 2700:
        raise ValueError("expected 2,700 fixed-revision Video-MME questions")
    return rows


def _video_mme_case(
    root: Path,
    registered: RegisteredCase,
    rows: dict[str, dict[str, object]],
) -> FormalCase:
    row = rows[registered.case_id]
    video_id = str(row["videoID"])
    source = root / "media" / "videomme" / f"{video_id}.mp4"
    if not source.is_file():
        raise ValueError(f"missing normalized Video-MME video {video_id}")
    duration, has_audio = _probe(source)
    duration_stratum = _actual_duration_stratum(duration)
    if duration_stratum != row["duration"]:
        raise ValueError(f"Video-MME duration stratum mismatch for {registered.case_id}")
    subtitle = root / "annotations" / "videomme-subtitles" / "subtitle" / f"{video_id}.srt"
    answer = str(row["answer"]).strip().removesuffix(".")
    raw_options = row["options"]
    if not isinstance(raw_options, list):
        raise ValueError(f"Video-MME options must be a list for {registered.case_id}")
    return FormalCase(
        case_id=f"videomme:{registered.case_id}",
        dataset="Video-MME",
        dataset_version=VIDEO_MME_REVISION,
        dataset_license=(
            "Academic research only; commercial use and re-sharing require permission."
        ),
        source_url=str(row["url"]),
        source=source,
        source_sha256=_sha256(source),
        question=str(row["question"]),
        options=_option_map(raw_options),
        answer=answer,
        subtitle_path=subtitle if subtitle.is_file() else None,
        has_audio=has_audio,
        duration_stratum=duration_stratum,
        requirements=registered.requirements,
        expected_tools=_expected_tools(registered.requirements),
    )


def _mvbench_case(
    root: Path,
    registered: RegisteredCase,
    rows: list[dict[str, object]],
) -> FormalCase:
    row_index = int(registered.case_id)
    row = rows[row_index]
    video_id = Path(str(row["video"])).stem
    source = root / "media" / "mvbench" / f"{video_id}.mp4"
    if not source.is_file():
        raise ValueError(f"missing MVBench video {video_id}")
    duration, has_audio = _probe(source)
    raw_candidates = row["candidates"]
    if not isinstance(raw_candidates, list):
        raise ValueError(f"MVBench candidates must be a list at row {row_index}")
    candidates = raw_candidates
    answer_text = str(row["answer"])
    try:
        answer_index = candidates.index(answer_text)
    except ValueError as error:
        raise ValueError(f"MVBench answer is not a candidate at row {row_index}") from error
    return FormalCase(
        case_id=f"mvbench:action_antonym:{row_index}",
        dataset="MVBench",
        dataset_version=(
            f"annotations:{MVBENCH_ANNOTATION_REVISION};video:{MVBENCH_VIDEO_REVISION}"
        ),
        dataset_license=(
            "MVBench metadata is MIT licensed; source videos retain source-dataset rights; "
            "internal non-commercial research only."
        ),
        source_url="https://huggingface.co/datasets/OpenGVLab/MVBench",
        source=source,
        source_sha256=_sha256(source),
        question=str(row["question"]),
        options=_option_map(candidates),
        answer=chr(ord("A") + answer_index),
        has_audio=has_audio,
        duration_stratum=_actual_duration_stratum(duration),
        requirements=registered.requirements,
        expected_tools=_expected_tools(registered.requirements),
    )


def prepare_manifests(root: Path) -> dict[str, Path]:
    """Create hash-bound smoke and formal manifests outside the repository."""
    root = root.resolve()
    video_mme_rows = _load_video_mme_rows(root)
    mvbench_path = root / "annotations" / "mvbench" / "action_antonym.json"
    mvbench_rows = json.loads(mvbench_path.read_text(encoding="utf-8"))
    if not isinstance(mvbench_rows, list) or len(mvbench_rows) != 200:
        raise ValueError("expected 200 fixed-revision MVBench action-antonym rows")
    manifests_dir = root / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for phase, selection in (("smoke", SMOKE_SELECTION), ("formal", FORMAL_SELECTION)):
        cases = [
            *(
                _video_mme_case(root, registered, video_mme_rows)
                for registered in selection["Video-MME"]
            ),
            *(_mvbench_case(root, registered, mvbench_rows) for registered in selection["MVBench"]),
        ]
        path = manifests_dir / f"{phase}.jsonl"
        path.write_text(
            "".join(case.model_dump_json() + "\n" for case in cases),
            encoding="utf-8",
        )
        result[phase] = path
    return result
