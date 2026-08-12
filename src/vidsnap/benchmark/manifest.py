"""Pre-registered public-case selection and external manifest preparation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vidsnap.benchmark.formal import (
    EvidenceRequirement,
    FormalCase,
    ToolAnnotationReason,
)
from vidsnap.contracts import AcquisitionTool

VIDEO_MME_REVISION = "ead1408f75b618502df9a1d8e0950166bf0a2a0b"
MVBENCH_ANNOTATION_REVISION = "230a2d4fac8900333c61754641c7a13e069ac9c6"
MVBENCH_VIDEO_REVISION = "a776e554280b99b70f00cc3eacd69a65e0727efc"
MVBENCH_TASK_SLUGS = {
    "Action Antonym": "action_antonym",
    "Action Sequence": "action_sequence",
    "Action Prediction": "action_prediction",
}
REGISTERED_MANIFEST_SHA256: dict[Literal["smoke", "formal"], str] = {
    "smoke": "e8e46847d2a9f1b7f53cf642b06eb9e92a8dec252df885b168ee33e87803b38a",
    "formal": "34e23c8bd588725cd6564152da34f0ea5d2f5063802a7f49b21b772adb951b74",
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class RegisteredCase:
    """One public case ID plus a human pre-registration of needed evidence."""

    case_id: str
    task_family: str
    requirements: tuple[EvidenceRequirement, ...]
    expected_tools: tuple[AcquisitionTool, ...]
    tool_annotation_reason: ToolAnnotationReason


def _registered(
    case_id: str,
    task_family: str,
    requirements: tuple[EvidenceRequirement, ...],
    expected_tools: tuple[AcquisitionTool, ...],
    tool_annotation_reason: ToolAnnotationReason,
) -> RegisteredCase:
    return RegisteredCase(
        case_id,
        task_family,
        requirements,
        expected_tools,
        tool_annotation_reason,
    )


FORMAL_SELECTION: dict[Literal["Video-MME", "MVBench"], tuple[RegisteredCase, ...]] = {
    "Video-MME": (
        _registered(
            "050-1",
            "Temporal Perception",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "050-2",
            "Temporal Perception",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "050-3", "Spatial Perception", ("speech",), ("transcribe_audio",), "speech-required"
        ),
        _registered(
            "119-1", "Information Synopsis", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "119-2", "Attribute Perception", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "119-3",
            "Information Synopsis",
            ("speech", "visual"),
            ("transcribe_audio", "sample_evidence"),
            "both-required",
        ),
        _registered(
            "212-1",
            "Action Recognition",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "212-2", "Object Reasoning", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "212-3", "Attribute Perception", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "007-1", "Action Recognition", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "007-2",
            "Temporal Reasoning",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered("007-3", "OCR Problems", ("visual",), ("sample_evidence",), "visual-required"),
        _registered(
            "527-1",
            "Temporal Reasoning",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "527-2", "Counting Problem", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered("527-3", "OCR Problems", ("visual",), ("sample_evidence",), "visual-required"),
        _registered("599-1", "OCR Problems", ("visual",), ("sample_evidence",), "visual-required"),
        _registered(
            "599-2",
            "Temporal Reasoning",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered("599-3", "OCR Problems", ("visual",), ("sample_evidence",), "visual-required"),
        _registered(
            "482-1",
            "Object Reasoning",
            ("speech", "visual"),
            ("transcribe_audio", "sample_evidence"),
            "both-required",
        ),
        _registered(
            "482-2", "OCR Problems", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "482-3", "Object Reasoning", ("speech",), ("transcribe_audio",), "speech-required"
        ),
        _registered(
            "428-1", "Information Synopsis", ("speech",), ("transcribe_audio",), "speech-required"
        ),
        _registered(
            "428-2", "Attribute Perception", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "428-3",
            "Object Reasoning",
            ("speech", "visual"),
            ("transcribe_audio", "sample_evidence"),
            "both-required",
        ),
        _registered(
            "673-1", "Information Synopsis", ("speech",), ("transcribe_audio",), "speech-required"
        ),
        _registered(
            "673-2",
            "Temporal Reasoning",
            ("speech", "temporal"),
            ("transcribe_audio", "sample_evidence"),
            "both-required",
        ),
        _registered(
            "673-3", "Object Reasoning", ("speech",), ("transcribe_audio",), "speech-required"
        ),
        _registered(
            "634-1", "Information Synopsis", ("speech",), ("transcribe_audio",), "speech-required"
        ),
        _registered(
            "634-2",
            "Temporal Reasoning",
            ("speech", "temporal"),
            ("transcribe_audio", "sample_evidence"),
            "both-required",
        ),
        _registered(
            "634-3", "Information Synopsis", ("speech",), ("transcribe_audio",), "speech-required"
        ),
        _registered(
            "743-1",
            "Object Reasoning",
            ("speech", "visual"),
            ("transcribe_audio", "sample_evidence"),
            "both-required",
        ),
        _registered(
            "743-2",
            "Counting Problem",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "743-3",
            "Action Reasoning",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "847-1", "Information Synopsis", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "847-2", "Spatial Reasoning", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "847-3",
            "Spatial Perception",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
    ),
    "MVBench": (
        _registered(
            "0", "Action Antonym", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "1", "Action Antonym", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "2", "Action Antonym", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "3", "Action Antonym", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "4", "Action Antonym", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "5", "Action Antonym", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "0", "Action Sequence", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "1", "Action Sequence", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "2", "Action Sequence", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "3", "Action Sequence", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "4", "Action Sequence", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "5", "Action Sequence", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "0",
            "Action Prediction",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "1",
            "Action Prediction",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "2",
            "Action Prediction",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "3",
            "Action Prediction",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "4",
            "Action Prediction",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "5",
            "Action Prediction",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
    ),
}

SMOKE_SELECTION: dict[Literal["Video-MME", "MVBench"], tuple[RegisteredCase, ...]] = {
    "Video-MME": (
        _registered(
            "069-2", "Object Recognition", ("visual",), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "395-2",
            "Action Recognition",
            ("visual", "temporal"),
            ("sample_evidence",),
            "visual-required",
        ),
        _registered(
            "419-1", "Information Synopsis", ("speech",), ("transcribe_audio",), "speech-required"
        ),
        _registered(
            "701-2",
            "Action Reasoning",
            ("speech", "temporal"),
            ("transcribe_audio", "sample_evidence"),
            "both-required",
        ),
    ),
    "MVBench": (
        _registered(
            "18", "Action Antonym", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
        _registered(
            "19", "Action Antonym", ("visual", "temporal"), ("sample_evidence",), "visual-required"
        ),
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
    if registered.task_family != row["task_type"]:
        raise ValueError(f"Video-MME task family mismatch for {registered.case_id}")
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
        task_family=registered.task_family,
        question=str(row["question"]),
        options=_option_map(raw_options),
        answer=answer,
        subtitle_path=subtitle if subtitle.is_file() else None,
        has_audio=has_audio,
        duration_stratum=duration_stratum,
        requirements=registered.requirements,
        expected_tools=registered.expected_tools,
        tool_annotation_reason=registered.tool_annotation_reason,
    )


def _mvbench_case(
    root: Path,
    registered: RegisteredCase,
    rows_by_task: dict[str, list[dict[str, object]]],
) -> FormalCase:
    task_slug = MVBENCH_TASK_SLUGS[registered.task_family]
    rows = rows_by_task[task_slug]
    row_index = int(registered.case_id)
    row = rows[row_index]
    video_id = Path(str(row["video"])).stem
    if task_slug == "action_antonym":
        normalized_name = f"{video_id}.mp4"
    else:
        normalized_name = f"{video_id}_{row['start']}_{row['end']}.mp4"
    source = root / "media" / "mvbench" / task_slug / normalized_name
    if not source.is_file():
        raise ValueError(f"missing MVBench video {task_slug}/{normalized_name}")
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
        case_id=f"mvbench:{task_slug}:{row_index}",
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
        task_family=registered.task_family,
        question=str(row["question"]),
        options=_option_map(candidates),
        answer=chr(ord("A") + answer_index),
        has_audio=has_audio,
        duration_stratum=_actual_duration_stratum(duration),
        requirements=registered.requirements,
        expected_tools=registered.expected_tools,
        tool_annotation_reason=registered.tool_annotation_reason,
    )


def prepare_manifests(root: Path) -> dict[str, Path]:
    """Create hash-bound smoke and formal manifests outside the repository."""
    root = root.resolve()
    try:
        root.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("benchmark root must be outside the repository")
    video_mme_rows = _load_video_mme_rows(root)
    mvbench_rows: dict[str, list[dict[str, object]]] = {}
    for task_slug in MVBENCH_TASK_SLUGS.values():
        task_path = root / "annotations" / "mvbench" / f"{task_slug}.json"
        task_rows = json.loads(task_path.read_text(encoding="utf-8"))
        if not isinstance(task_rows, list) or len(task_rows) != 200:
            raise ValueError(f"expected 200 fixed-revision MVBench {task_slug} rows")
        mvbench_rows[task_slug] = task_rows
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
