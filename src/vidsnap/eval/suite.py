"""The ``vidsnap.eval-suite/v1`` eval set format, its loader and its validator.

An eval set is one JSON file per task. Items reference source media by a path
relative to a media root plus provenance (URL, SHA-256, duration, licence); no
media is committed. Synthetic items point at a ``vidsnap.eval-synthetic/v1``
storyboard spec, from which both the media and the reference transcript derive.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator
from typing_extensions import Self

from vidsnap.contracts.models import StrictModel

SUITE_SCHEMA = "vidsnap.eval-suite/v1"
SYNTHETIC_SCHEMA = "vidsnap.eval-synthetic/v1"
MEDIA_ROOT_ENV = "VIDSNAP_EVAL_MEDIA_ROOT"

TaskId = Literal["t1", "t2a", "t2b", "t3"]
ItemStatus = Literal["ready", "needs_reference", "placeholder"]
SourceKind = Literal["synthetic", "public", "owner"]
Language = Literal["zh", "en"]
KeyPointModality = Literal["speech", "visual", "both"]

_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"


def _check_relative(value: str | None) -> str | None:
    """Accept only a plain relative POSIX path without parent traversal."""
    if value is None:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or not value.strip():
        raise ValueError("path must be relative, POSIX-style and free of '..'")
    return value


Groups = list[list[str]]


def _check_groups(groups: Groups) -> Groups:
    if not groups:
        raise ValueError("at least one keyword group is required")
    for group in groups:
        if not group or any(not alternative.strip() for alternative in group):
            raise ValueError("every keyword group needs non-empty alternatives")
    return groups


class ClipWindow(StrictModel):
    """A window cut from the source before the run."""

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("clip end must be after its start")
        return self


class SourceVideo(StrictModel):
    """Where an item's video comes from and how to recognise the exact bytes."""

    kind: SourceKind
    path: str | None = None
    url: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    bytes: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    licence: str = Field(min_length=1, max_length=500)
    attribution: str | None = Field(default=None, max_length=500)
    generator: str | None = None
    clip: ClipWindow | None = None
    language: Language
    has_audio: bool | None = None

    _relative_path = field_validator("path", "generator")(_check_relative)


class TranscriptSegment(StrictModel):
    """One timed span of the reference transcript."""

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str = Field(min_length=1)
    speaker: str | None = None


class ReferenceTranscript(StrictModel):
    """Timed reference transcript; synthetic items derive it from their spec."""

    language: Language
    from_generator: bool = False
    segments: list[TranscriptSegment] = Field(default_factory=list)

    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments)


class KeyPoint(StrictModel):
    """A fact a good output must state; matched by keyword groups."""

    id: str = Field(pattern=_ID_PATTERN)
    text: str = Field(min_length=1)
    match: Groups
    modality: KeyPointModality = "both"
    window: tuple[float, float] | None = None
    weight: float = Field(default=1.0, gt=0)

    _groups = field_validator("match")(_check_groups)


class KeyMoment(StrictModel):
    """A timestamp an output figure, scene or claim should point at."""

    id: str = Field(pattern=_ID_PATTERN)
    at_seconds: float = Field(ge=0)
    tolerance_seconds: float = Field(default=5.0, gt=0)
    description: str = Field(min_length=1)


class ForbiddenStatement(StrictModel):
    """A statement that would be a hallucination for this video."""

    id: str = Field(pattern=_ID_PATTERN)
    text: str = Field(min_length=1)
    match: Groups

    _groups = field_validator("match")(_check_groups)


class ReferenceQuestion(StrictModel):
    """One wrong question a teacher recording explains (task t3)."""

    id: str = Field(pattern=_ID_PATTERN)
    stem: str = Field(min_length=1)
    stem_match: Groups
    answer: str = Field(min_length=1)
    answer_match: Groups
    mistake: str = Field(min_length=1)
    mistake_match: Groups
    window: tuple[float, float]

    _groups = field_validator("stem_match", "answer_match", "mistake_match")(_check_groups)


class Reference(StrictModel):
    """Reference outputs; empty lists mean the reference is not written yet."""

    transcript: ReferenceTranscript | None = None
    key_points: list[KeyPoint] = Field(default_factory=list)
    key_moments: list[KeyMoment] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    forbidden: list[ForbiddenStatement] = Field(default_factory=list)
    questions: list[ReferenceQuestion] = Field(default_factory=list)


class ItemInputs(StrictModel):
    """What the system is asked to do for this item."""

    goal: str = Field(min_length=1, max_length=2000)
    topic: str | None = Field(default=None, max_length=500)
    audience: str | None = Field(default=None, max_length=500)


class EvalItem(StrictModel):
    """One evaluation item: a source video, inputs and reference outputs."""

    item_id: str = Field(pattern=_ID_PATTERN)
    status: ItemStatus
    source: SourceVideo
    inputs: ItemInputs
    reference: Reference = Field(default_factory=Reference)
    notes: str | None = Field(default=None, max_length=4000)


class EvalSuite(StrictModel):
    """A ``vidsnap.eval-suite/v1`` document."""

    schema_version: Literal["vidsnap.eval-suite/v1"]
    suite_id: str = Field(pattern=_ID_PATTERN)
    task: TaskId
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    items: list[EvalItem] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> Self:
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("item_id values must be unique")
        return self


class SyntheticSlide(StrictModel):
    """One slide of a synthetic recording: what is shown and what is said."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    lines: list[str] = Field(min_length=1)
    narration: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0, le=600)
    voice: str | None = None
    speaker: str | None = None


class SyntheticSpec(StrictModel):
    """A ``vidsnap.eval-synthetic/v1`` storyboard that generates one video."""

    schema_version: Literal["vidsnap.eval-synthetic/v1"]
    id: str = Field(pattern=_ID_PATTERN)
    language: Language
    voice: str = Field(min_length=1)
    width: int = Field(default=1280, ge=160, le=3840)
    height: int = Field(default=720, ge=90, le=2160)
    output: str
    slides: list[SyntheticSlide] = Field(min_length=1)

    _relative_output = field_validator("output")(_check_relative)

    def segments(self) -> list[TranscriptSegment]:
        """Slide windows with their exact narration, in timeline order."""
        segments: list[TranscriptSegment] = []
        start = 0.0
        for slide in self.slides:
            end = start + slide.duration_seconds
            segments.append(
                TranscriptSegment(
                    start_seconds=round(start, 3),
                    end_seconds=round(end, 3),
                    text=slide.narration,
                    speaker=slide.speaker,
                )
            )
            start = end
        return segments

    def duration_seconds(self) -> float:
        return round(sum(slide.duration_seconds for slide in self.slides), 3)


@dataclass(frozen=True, slots=True)
class LoadedSuite:
    """A validated suite plus where it came from and the exact bytes' digest."""

    suite: EvalSuite
    path: Path
    sha256: str
    specs: dict[str, SyntheticSpec] = field(default_factory=dict)

    @property
    def eval_root(self) -> Path:
        """The directory generator paths are relative to (the suites' parent)."""
        return self.path.parent.parent


@dataclass(frozen=True, slots=True)
class SuiteIssue:
    """One validation finding; ``error`` blocks a run of that item."""

    level: Literal["error", "warning", "info"]
    item_id: str | None
    message: str


def default_suites_dir() -> Path:
    """``benchmarks/eval/suites`` of the current working tree."""
    return Path("benchmarks") / "eval" / "suites"


def default_media_root(suite_path: Path) -> Path:
    """The media root: the environment variable, else ``<suites>/../media``."""
    configured = os.environ.get(MEDIA_ROOT_ENV)
    if configured:
        return Path(configured).expanduser()
    return suite_path.parent.parent / "media"


def resolve_suite_path(reference: str, suites_dir: Path | None = None) -> Path:
    """Resolve a suite name such as ``t1`` or a path to a suite file."""
    candidate = Path(reference).expanduser()
    if candidate.suffix == ".json" or candidate.exists():
        return candidate
    return (suites_dir or default_suites_dir()) / f"{reference}.json"


def load_suite(reference: str | Path, suites_dir: Path | None = None) -> LoadedSuite:
    """Load and validate one suite; raise ``ValueError`` with a short reason."""
    path = resolve_suite_path(str(reference), suites_dir).resolve()
    try:
        raw = path.read_bytes()
        suite = EvalSuite.model_validate(json.loads(raw.decode("utf-8")))
    except FileNotFoundError:
        raise ValueError(f"suite not found: {path}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"suite is invalid: {path}: {_short_error(error)}") from None
    specs: dict[str, SyntheticSpec] = {}
    items: list[EvalItem] = []
    for item in suite.items:
        if item.source.generator is not None:
            spec = load_synthetic_spec(path.parent.parent / item.source.generator)
            specs[item.item_id] = spec
            item = _with_generated_transcript(item, spec)
        items.append(item)
    suite = suite.model_copy(update={"items": items})
    return LoadedSuite(suite=suite, path=path, sha256=hashlib.sha256(raw).hexdigest(), specs=specs)


def load_synthetic_spec(path: Path) -> SyntheticSpec:
    """Load one synthetic storyboard spec."""
    try:
        return SyntheticSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        raise ValueError(f"synthetic spec not found: {path}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"synthetic spec is invalid: {path}: {_short_error(error)}") from None


def _with_generated_transcript(item: EvalItem, spec: SyntheticSpec) -> EvalItem:
    transcript = item.reference.transcript
    if transcript is None or not transcript.from_generator:
        return item
    generated = ReferenceTranscript(
        language=transcript.language, from_generator=True, segments=spec.segments()
    )
    reference = item.reference.model_copy(update={"transcript": generated})
    return item.model_copy(update={"reference": reference})


def resolve_media(item: EvalItem, media_root: Path) -> Path | None:
    """Return the item's local media path under the media root, if it has one."""
    if item.source.path is None:
        return None
    return media_root / item.source.path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_suite(
    loaded: LoadedSuite, media_root: Path | None = None, *, check_hashes: bool = True
) -> list[SuiteIssue]:
    """Report placeholders, missing references, inconsistent references and media state."""
    issues: list[SuiteIssue] = []
    task = loaded.suite.task
    for item in loaded.suite.items:
        issues.extend(_item_issues(item, task, loaded.specs.get(item.item_id)))
        if media_root is not None and item.status != "placeholder":
            issues.extend(_media_issues(item, media_root, check_hashes=check_hashes))
    return issues


def _item_issues(item: EvalItem, task: TaskId, spec: SyntheticSpec | None) -> list[SuiteIssue]:
    issues: list[SuiteIssue] = []
    item_id = item.item_id
    source = item.source
    reference = item.reference
    if item.status == "placeholder":
        issues.append(
            SuiteIssue("info", item_id, "placeholder: waiting for the owner's video (see notes)")
        )
        return issues
    if source.path is None:
        issues.append(SuiteIssue("error", item_id, "source.path is required unless placeholder"))
    if source.kind == "synthetic" and spec is None:
        issues.append(SuiteIssue("error", item_id, "synthetic items need source.generator"))
    if source.kind != "synthetic" and source.sha256 is None:
        issues.append(SuiteIssue("error", item_id, "public and owner items need source.sha256"))
    duration = source.duration_seconds
    if spec is not None:
        duration = spec.duration_seconds()
    if source.clip is not None:
        duration = source.clip.end_seconds - source.clip.start_seconds
    has_reference = bool(reference.key_points or reference.questions)
    if item.status == "ready" and not has_reference:
        issues.append(SuiteIssue("error", item_id, "ready items need key points or questions"))
    if item.status == "needs_reference":
        issues.append(SuiteIssue("info", item_id, "reference outputs not written yet"))
    if task == "t3" and item.status == "ready" and not reference.questions:
        issues.append(SuiteIssue("error", item_id, "t3 items need reference questions"))
    if task == "t2b" and duration is not None and duration > 120:
        issues.append(SuiteIssue("error", item_id, "t2b clips must be at most 120 s"))
    if task == "t2a" and not item.inputs.topic:
        issues.append(SuiteIssue("warning", item_id, "t2a items should state a topic"))
    if duration is not None:
        for moment in reference.key_moments:
            if moment.at_seconds > duration:
                issues.append(SuiteIssue("error", item_id, f"key moment {moment.id} > duration"))
        for point in reference.key_points:
            if point.window is not None and point.window[0] > duration:
                issues.append(SuiteIssue("error", item_id, f"key point {point.id} window > end"))
        for question in reference.questions:
            if question.window[0] > duration:
                issues.append(SuiteIssue("error", item_id, f"question {question.id} window > end"))
    ids = [point.id for point in reference.key_points] + [m.id for m in reference.key_moments]
    if len(ids) != len(set(ids)):
        issues.append(SuiteIssue("error", item_id, "key point and moment ids must be unique"))
    if (
        reference.transcript is not None
        and not reference.transcript.segments
        and item.status == "ready"
    ):
        issues.append(SuiteIssue("warning", item_id, "reference transcript has no segments"))
    return issues


def _media_issues(item: EvalItem, media_root: Path, *, check_hashes: bool) -> list[SuiteIssue]:
    path = resolve_media(item, media_root)
    if path is None:
        return []
    if not path.is_file():
        level: Literal["error", "warning"] = (
            "warning" if item.source.kind == "synthetic" else "error"
        )
        hint = (
            "run scripts/eval/make_synthetic_media.py"
            if item.source.kind == "synthetic"
            else "download it from source.url"
        )
        return [SuiteIssue(level, item.item_id, f"media missing at {path}; {hint}")]
    if not check_hashes or item.source.sha256 is None:
        return []
    actual = file_sha256(path)
    if actual == item.source.sha256:
        return []
    if item.source.kind == "synthetic":
        return [
            SuiteIssue(
                "warning",
                item.item_id,
                "synthetic media differs from the recorded SHA-256 (TTS/FFmpeg version); "
                "the actual hash is recorded with each result",
            )
        ]
    return [SuiteIssue("error", item.item_id, "media SHA-256 does not match the manifest")]


def _short_error(error: BaseException) -> str:
    if isinstance(error, ValidationError):
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        return f"{location}: {first['msg']}"
    return type(error).__name__
