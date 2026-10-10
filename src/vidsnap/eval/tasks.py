"""The four evaluated tasks: output schemas, prompts, verifier gates and mock outputs.

The harness and native systems receive the same task instructions and the same
output schema; only the input path differs (typed evidence vs the whole video).
Output models ignore unknown fields and accept ``MM:SS`` timestamps for both
systems alike, so the comparison is about content rather than JSON pedantry.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BeforeValidator, ConfigDict, Field

from vidsnap.contracts import Evidence
from vidsnap.contracts.models import StrictModel
from vidsnap.eval.suite import EvalItem, TaskId
from vidsnap.eval.text import cjk_ratio, parse_timestamp

PROMPT_VERSION = "eval-prompts/2026-10-10"

Seconds = Annotated[float, BeforeValidator(parse_timestamp)]


class EvalOutput(StrictModel):
    """Lenient base for model outputs: unknown fields are ignored, not fatal."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class Figure(EvalOutput):
    timestamp_seconds: Seconds
    caption: str = Field(min_length=1)
    evidence_id: str | None = None


class ArticleSection(EvalOutput):
    heading: str = Field(min_length=1)
    body: str = Field(min_length=1)
    figures: list[Figure] = Field(default_factory=list)


class ArticleOutput(EvalOutput):
    """Task t1: an illustrated WeChat-style article."""

    title: str = Field(min_length=1)
    intro: str = Field(min_length=1)
    takeaways: list[str] = Field(default_factory=list)
    sections: list[ArticleSection] = Field(min_length=1)
    summary: str = Field(min_length=1)


class Caption(EvalOutput):
    start_seconds: Seconds
    end_seconds: Seconds
    text: str = Field(min_length=1)


class Scene(EvalOutput):
    title: str = Field(min_length=1)
    start_seconds: Seconds
    end_seconds: Seconds
    captions: list[Caption] = Field(min_length=1)
    on_screen_text: list[str] = Field(default_factory=list)
    visual: str = ""
    source_timestamps: list[Seconds] = Field(default_factory=list)


class StoryboardOutput(EvalOutput):
    """Task t2a (and the video part of t3): a timeline storyboard."""

    title: str = Field(min_length=1)
    scenes: list[Scene] = Field(min_length=1)


class ReviewClaim(EvalOutput):
    text: str = Field(min_length=1)
    start_seconds: Seconds
    end_seconds: Seconds
    evidence_ids: list[str] = Field(default_factory=list)


class ClipReviewOutput(EvalOutput):
    """Task t2b: a summary and timed claims for a clip of at most 120 s."""

    summary: str = Field(min_length=1)
    claims: list[ReviewClaim] = Field(min_length=1)


class WrongQuestion(EvalOutput):
    stem: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list)
    correct_answer: str = Field(min_length=1)
    common_mistake: str = Field(min_length=1)
    solution_steps: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    start_seconds: Seconds
    end_seconds: Seconds
    frame_timestamp_seconds: Seconds
    frame_evidence_id: str | None = None


class StudyNotes(EvalOutput):
    title: str = Field(min_length=1)
    sections: list[ArticleSection] = Field(min_length=1)
    summary: str = Field(min_length=1)


class LessonOutput(EvalOutput):
    """Task t3: wrong questions, illustrated notes and a teaching-video storyboard."""

    wrong_questions: list[WrongQuestion] = Field(min_length=1)
    notes: StudyNotes
    video: StoryboardOutput


OutputT = TypeVar("OutputT", bound=EvalOutput)

_HARNESS_RULES = (
    "你看不到原视频，只能看到运行时提供的证据：transcript 证据是语音转写文本，"
    "frame 证据是按顺序附上的关键帧图片，每个证据都有 id 和 start_seconds。"
    "只依据这些证据写作，不要编造证据里没有的内容。"
    "凡是需要时间戳的字段，都用相关证据的秒数；凡是引用画面的地方，"
    "填写对应 frame 证据的 id（evidence_id / frame_evidence_id / evidence_ids）。"
)
_NATIVE_RULES = (
    "你会直接看到完整的视频（含画面和声音）。只依据视频内容写作，不要编造。"
    "所有时间戳都用从视频开头算起的秒数（数字）。"
)
_JSON_RULES = (
    "只输出一个严格的 JSON 对象，不要 Markdown 代码块，不要任何解释文字。"
    "所有面向读者的文字用简体中文；人名、产品名、公式和数字保持原样。"
)


class EvalTask(ABC, Generic[OutputT]):
    """One evaluated task; subclasses fix the schema, prompt and checks."""

    task_id: TaskId
    output_model: type[OutputT]
    goal_prefix: str

    def instructions(self, item: EvalItem, *, harness: bool) -> str:
        """The full task prompt for one item and one input path."""
        parts = [
            self.goal_prefix,
            f"本条目的具体要求：{item.inputs.goal}",
        ]
        if item.inputs.topic:
            parts.append(f"讲解主题：{item.inputs.topic}")
        if item.inputs.audience:
            parts.append(f"目标读者：{item.inputs.audience}")
        parts.append(_HARNESS_RULES if harness else _NATIVE_RULES)
        parts.append(_JSON_RULES)
        parts.append("JSON 结构如下（字段名必须一致）：\n" + self.schema_hint(harness=harness))
        return "\n\n".join(parts)

    @abstractmethod
    def schema_hint(self, *, harness: bool) -> str:
        """A compact JSON skeleton describing the expected fields."""

    def parse(self, payload: dict[str, Any]) -> OutputT:
        return self.output_model.model_validate(payload)

    @abstractmethod
    def gates(
        self, output: OutputT, evidence: Sequence[Evidence], duration: float, *, harness: bool
    ) -> dict[str, bool]:
        """Deterministic verifier gates; evidence gates apply to the harness only."""

    @abstractmethod
    def mock_output(
        self, evidence: Sequence[Evidence], duration: float, item: EvalItem | None
    ) -> OutputT:
        """A deterministic, schema-valid output for offline runs."""

    @abstractmethod
    def text(self, output: OutputT) -> str:
        """All reader-facing text, for key-point and entity matching."""

    @abstractmethod
    def spans(self, output: OutputT) -> list[tuple[float, float]]:
        """Source-video time spans the output points at, for moment recall."""

    @abstractmethod
    def structure(self, output: OutputT, duration: float) -> dict[str, bool]:
        """The task's structure checks."""

    def timestamps(self, output: OutputT) -> list[float]:
        values: list[float] = []
        for start, end in self.spans(output):
            values.append(start)
            if end != start:
                values.append(end)
        return values


def _in_bounds(values: Sequence[float], duration: float) -> bool:
    return all(0 <= value <= duration + 0.5 for value in values)


def _frame_ids(evidence: Sequence[Evidence]) -> set[str]:
    return {item.id for item in evidence if item.modality == "frame"}


def _transcript_text(evidence: Sequence[Evidence]) -> str:
    return "\n".join(item.content or "" for item in evidence if item.modality == "transcript")


def _sentences(text: str, count: int) -> list[str]:
    pieces = [piece.strip() for piece in re.split(r"[。！？!?.\n]+", text) if piece.strip()]
    return pieces[:count]


def _mock_moments(evidence: Sequence[Evidence], duration: float, count: int) -> list[Evidence]:
    frames = [item for item in evidence if item.modality == "frame"]
    if frames:
        step = max(1, len(frames) // count)
        return frames[::step][:count]
    return []


def _mock_times(duration: float, count: int) -> list[float]:
    return [round(duration * (index + 1) / (count + 1), 3) for index in range(count)]


def _figures(
    evidence: Sequence[Evidence], duration: float, count: int, caption: str
) -> list[Figure]:
    frames = _mock_moments(evidence, duration, count)
    if frames:
        return [
            Figure(timestamp_seconds=frame.start_seconds, caption=caption, evidence_id=frame.id)
            for frame in frames
        ]
    return [
        Figure(timestamp_seconds=time, caption=caption) for time in _mock_times(duration, count)
    ]


def _section_text(section: ArticleSection) -> str:
    captions = " ".join(figure.caption for figure in section.figures)
    return f"{section.heading}\n{section.body}\n{captions}"


def _storyboard_text(storyboard: StoryboardOutput) -> str:
    lines = [storyboard.title]
    for scene in storyboard.scenes:
        lines.append(scene.title)
        lines.extend(caption.text for caption in scene.captions)
        lines.extend(scene.on_screen_text)
    return "\n".join(lines)


def storyboard_checks(storyboard: StoryboardOutput) -> dict[str, bool]:
    """Timeline rules shared by t2a and the t3 teaching video."""
    scenes = storyboard.scenes
    captions = [caption for scene in scenes for caption in scene.captions]
    ordered = sorted(captions, key=lambda caption: caption.start_seconds)
    return {
        "scene_count_3_to_15": 3 <= len(scenes) <= 15,
        "scene_length_6_to_40s": all(
            6 <= scene.end_seconds - scene.start_seconds <= 40 for scene in scenes
        ),
        "scenes_ordered": all(
            later.start_seconds >= earlier.end_seconds - 0.5
            for earlier, later in zip(scenes, scenes[1:])
        ),
        "captions_at_most_6s": all(
            0 < caption.end_seconds - caption.start_seconds <= 6 for caption in captions
        ),
        "captions_short": all(len(caption.text) <= 40 for caption in captions),
        "captions_inside_scenes": all(
            scene.start_seconds - 0.5 <= caption.start_seconds
            and caption.end_seconds <= scene.end_seconds + 0.5
            for scene in scenes
            for caption in scene.captions
        ),
        "captions_do_not_overlap": all(
            later.start_seconds >= earlier.end_seconds - 0.05
            for earlier, later in zip(ordered, ordered[1:])
        ),
    }


def _mock_storyboard(
    title: str, sentences: Sequence[str], sources: Sequence[float]
) -> StoryboardOutput:
    scenes: list[Scene] = []
    for index in range(3):
        start = index * 12.0
        text = sentences[index] if index < len(sentences) else f"第{index + 1}部分"
        scenes.append(
            Scene(
                title=f"第{index + 1}幕",
                start_seconds=start,
                end_seconds=start + 12.0,
                captions=[
                    Caption(start_seconds=start + 1, end_seconds=start + 5, text=text[:40]),
                    Caption(start_seconds=start + 6, end_seconds=start + 11, text="（模拟字幕）"),
                ],
                on_screen_text=[text[:20]],
                visual="模拟画面",
                source_timestamps=[sources[index]] if index < len(sources) else [],
            )
        )
    return StoryboardOutput(title=title, scenes=scenes)


class ArticleTask(EvalTask[ArticleOutput]):
    task_id: TaskId = "t1"
    output_model = ArticleOutput
    goal_prefix = (
        "任务：把这个长视频改写成一篇图文并茂的微信公众号文章。要求：一个吸引人的标题；"
        "一段引言；3 到 10 条核心要点；至少 3 个小节，每节有小标题和正文；"
        "全文至少 3 张配图，配图选自视频中最能说明该节内容的画面，每张配图写一句图注"
        "（说明画面内容，而不是只写时间）；最后一段总结。内容必须忠实于视频，"
        "人名、数字、专有名词要准确。"
    )

    def schema_hint(self, *, harness: bool) -> str:
        figure = (
            '{"timestamp_seconds": 12.5, "caption": "图注", "evidence_id": "frame-001"}'
            if harness
            else '{"timestamp_seconds": 12.5, "caption": "图注"}'
        )
        return (
            '{"title": "标题", "intro": "引言", "takeaways": ["要点1", "要点2", "要点3"], '
            '"sections": [{"heading": "小标题", "body": "正文", "figures": ['
            + figure
            + ']}], "summary": "总结"}'
        )

    def gates(
        self, output: ArticleOutput, evidence: Sequence[Evidence], duration: float, *, harness: bool
    ) -> dict[str, bool]:
        figures = [figure for section in output.sections for figure in section.figures]
        gates = {
            "schema_valid": True,
            "figures_present": bool(figures),
            "timestamps_in_bounds": _in_bounds([f.timestamp_seconds for f in figures], duration),
        }
        if harness:
            frame_ids = _frame_ids(evidence)
            gates["referenced_evidence_exists"] = all(
                figure.evidence_id in frame_ids for figure in figures
            )
        return gates

    def mock_output(
        self, evidence: Sequence[Evidence], duration: float, item: EvalItem | None
    ) -> ArticleOutput:
        sentences = _sentences(_transcript_text(evidence), 6) or ["模拟内容"]
        figures = _figures(evidence, duration, 3, "模拟图注：视频画面")
        sections = [
            ArticleSection(
                heading=f"第{index + 1}节",
                body=sentences[index % len(sentences)],
                figures=[figures[index]] if index < len(figures) else [],
            )
            for index in range(3)
        ]
        return ArticleOutput(
            title=f"模拟文章：{sentences[0][:16]}",
            intro=sentences[0],
            takeaways=[sentence[:30] for sentence in (sentences * 3)[:3]],
            sections=sections,
            summary=sentences[-1],
        )

    def text(self, output: ArticleOutput) -> str:
        parts = [output.title, output.intro, *output.takeaways]
        parts.extend(_section_text(section) for section in output.sections)
        parts.append(output.summary)
        return "\n".join(parts)

    def spans(self, output: ArticleOutput) -> list[tuple[float, float]]:
        return [
            (figure.timestamp_seconds, figure.timestamp_seconds)
            for section in output.sections
            for figure in section.figures
        ]

    def structure(self, output: ArticleOutput, duration: float) -> dict[str, bool]:
        figures = [figure for section in output.sections for figure in section.figures]
        times = sorted(figure.timestamp_seconds for figure in figures)
        prose = self.text(output)
        return {
            "title_present": 4 <= len(output.title) <= 64,
            "intro_present": len(output.intro) >= 20,
            "takeaways_3_to_10": 3 <= len(output.takeaways) <= 10,
            "sections_at_least_3": len(output.sections) >= 3,
            "figures_at_least_3": len(figures) >= 3,
            "captions_describe_content": all(
                len(figure.caption) >= 6 and not re.fullmatch(r"[\d:：\s]+", figure.caption)
                for figure in figures
            )
            and bool(figures),
            "figures_spread_over_half": bool(times)
            and duration > 0
            and (times[-1] - times[0]) >= 0.5 * duration,
            "mostly_chinese": cjk_ratio(prose) >= 0.6,
            "summary_60_to_800_chars": 60 <= len(output.summary) <= 800,
        }


class ExplainerTask(EvalTask[StoryboardOutput]):
    task_id: TaskId = "t2a"
    output_model = StoryboardOutput
    goal_prefix = (
        "任务：以这个视频为素材，为给定主题制作一条讲解视频的分镜脚本（后续会渲染成 HTML "
        "时间轴动画）。要求：3 到 15 个场景，每个场景只讲一个概念，时长 6 到 40 秒；"
        "字幕（captions）是旁白的唯一来源，每条字幕不超过 6 秒、不超过 40 个字，"
        "字幕不重叠且落在所属场景时间内；场景时间是讲解视频自己的时间轴（从 0 开始）；"
        "on_screen_text 写画面上要出现的文字；visual 描述画面；source_timestamps 写该场景"
        "依据的素材视频时间点（秒）。讲解要从原理出发、用素材里的真实数字，不要编造。"
    )

    def schema_hint(self, *, harness: bool) -> str:
        del harness
        return (
            '{"title": "片名", "scenes": [{"title": "场景标题", "start_seconds": 0, '
            '"end_seconds": 18, "captions": [{"start_seconds": 0.5, "end_seconds": 4.5, '
            '"text": "字幕"}], "on_screen_text": ["画面文字"], "visual": "画面描述", '
            '"source_timestamps": [12.0]}]}'
        )

    def gates(
        self,
        output: StoryboardOutput,
        evidence: Sequence[Evidence],
        duration: float,
        *,
        harness: bool,
    ) -> dict[str, bool]:
        del evidence, harness
        sources = [time for scene in output.scenes for time in scene.source_timestamps]
        return {
            "schema_valid": True,
            "timestamps_in_bounds": _in_bounds(sources, duration),
        }

    def mock_output(
        self, evidence: Sequence[Evidence], duration: float, item: EvalItem | None
    ) -> StoryboardOutput:
        sentences = _sentences(_transcript_text(evidence), 3)
        frames = _mock_moments(evidence, duration, 3)
        sources = [frame.start_seconds for frame in frames] or _mock_times(duration, 3)
        topic = item.inputs.topic if item is not None and item.inputs.topic else "模拟主题"
        return _mock_storyboard(f"讲解：{topic}", sentences, sources)

    def text(self, output: StoryboardOutput) -> str:
        return _storyboard_text(output)

    def spans(self, output: StoryboardOutput) -> list[tuple[float, float]]:
        return [(time, time) for scene in output.scenes for time in scene.source_timestamps]

    def timestamps(self, output: StoryboardOutput) -> list[float]:
        return [time for scene in output.scenes for time in scene.source_timestamps]

    def structure(self, output: StoryboardOutput, duration: float) -> dict[str, bool]:
        checks = storyboard_checks(output)
        checks["scenes_cite_source"] = all(scene.source_timestamps for scene in output.scenes)
        return checks


class ClipReviewTask(EvalTask[ClipReviewOutput]):
    task_id: TaskId = "t2b"
    output_model = ClipReviewOutput
    goal_prefix = (
        "任务：为这段播客/访谈片段（不超过 120 秒）写一份点评：一段 80 到 400 字的概括，"
        "以及 3 到 8 条具体观点（claims），每条观点写清楚是谁说的或画面显示了什么，"
        "并给出它在片段中的起止时间（秒）。只写片段里真正出现的内容。"
    )

    def schema_hint(self, *, harness: bool) -> str:
        evidence = ', "evidence_ids": ["transcript-001"]' if harness else ""
        return (
            '{"summary": "概括", "claims": [{"text": "观点", "start_seconds": 10.0, '
            '"end_seconds": 18.0' + evidence + "}]}"
        )

    def gates(
        self,
        output: ClipReviewOutput,
        evidence: Sequence[Evidence],
        duration: float,
        *,
        harness: bool,
    ) -> dict[str, bool]:
        gates = {
            "schema_valid": True,
            "timestamps_in_bounds": _in_bounds(self.timestamps(output), duration),
            "spans_ordered": all(
                claim.end_seconds >= claim.start_seconds for claim in output.claims
            ),
        }
        if harness:
            known = {item.id for item in evidence}
            gates["claims_cite_evidence"] = all(
                claim.evidence_ids and set(claim.evidence_ids) <= known for claim in output.claims
            )
        return gates

    def mock_output(
        self, evidence: Sequence[Evidence], duration: float, item: EvalItem | None
    ) -> ClipReviewOutput:
        sentences = _sentences(_transcript_text(evidence), 4) or ["模拟观点"]
        ids = [entry.id for entry in evidence][:1]
        claims = []
        for index, time in enumerate(_mock_times(duration, 3)):
            claims.append(
                ReviewClaim(
                    text=sentences[index % len(sentences)],
                    start_seconds=max(0.0, time - 2),
                    end_seconds=min(duration, time + 2),
                    evidence_ids=list(ids),
                )
            )
        return ClipReviewOutput(summary="模拟概括：" + "；".join(sentences), claims=claims)

    def text(self, output: ClipReviewOutput) -> str:
        return "\n".join([output.summary, *(claim.text for claim in output.claims)])

    def spans(self, output: ClipReviewOutput) -> list[tuple[float, float]]:
        return [(claim.start_seconds, claim.end_seconds) for claim in output.claims]

    def structure(self, output: ClipReviewOutput, duration: float) -> dict[str, bool]:
        return {
            "summary_80_to_400_chars": 80 <= len(output.summary) <= 400,
            "claims_3_to_8": 3 <= len(output.claims) <= 8,
            "claim_spans_valid": all(
                0 <= claim.start_seconds <= claim.end_seconds <= duration + 0.5
                for claim in output.claims
            ),
            "mostly_chinese": cjk_ratio(self.text(output)) >= 0.6,
        }


class LessonTask(EvalTask[LessonOutput]):
    task_id: TaskId = "t3"
    output_model = LessonOutput
    goal_prefix = (
        "任务：这是一段老师讲解试题的录屏。请完成三件事：\n"
        "1. wrong_questions：提取老师讲到的每一道错题，写出题干（stem）、选项（如有）、"
        "正确答案、学生常见错误（common_mistake）、解题步骤、知识点，以及该题讲解的起止时间"
        "和最能展示题目的画面时间点（frame_timestamp_seconds）。\n"
        "2. notes：一份图文学习笔记，至少 2 个小节，每节配 1 张图并写图注，最后写总结。\n"
        "3. video：一条给初中生看的 HTML 教学视频分镜，规则同讲解视频：3 到 15 个场景，"
        "每个场景 6 到 40 秒，字幕是旁白唯一来源，每条不超过 6 秒、40 个字，不重叠；"
        "场景时间是教学视频自己的时间轴，source_timestamps 写依据的录屏时间点。\n"
        "答案和解题步骤必须正确；录屏里没有的题目不要编造。"
    )

    def schema_hint(self, *, harness: bool) -> str:
        frame = ', "frame_evidence_id": "frame-002"' if harness else ""
        figure = (
            '{"timestamp_seconds": 30.0, "caption": "图注", "evidence_id": "frame-002"}'
            if harness
            else '{"timestamp_seconds": 30.0, "caption": "图注"}'
        )
        return (
            '{"wrong_questions": [{"stem": "题干", "options": [], "correct_answer": "答案", '
            '"common_mistake": "常见错误", "solution_steps": ["步骤"], '
            '"knowledge_points": ["知识点"], "start_seconds": 20.0, "end_seconds": 60.0, '
            '"frame_timestamp_seconds": 25.0' + frame + "}], "
            '"notes": {"title": "笔记标题", "sections": [{"heading": "小标题", "body": "正文", '
            '"figures": [' + figure + ']}], "summary": "总结"}, '
            '"video": {"title": "片名", "scenes": [{"title": "场景", "start_seconds": 0, '
            '"end_seconds": 15, "captions": [{"start_seconds": 0.5, "end_seconds": 4.5, '
            '"text": "字幕"}], "on_screen_text": [], "visual": "", "source_timestamps": [25.0]}]}}'
        )

    def gates(
        self, output: LessonOutput, evidence: Sequence[Evidence], duration: float, *, harness: bool
    ) -> dict[str, bool]:
        gates = {
            "schema_valid": True,
            "timestamps_in_bounds": _in_bounds(self.timestamps(output), duration),
        }
        if harness:
            frame_ids = _frame_ids(evidence)
            references = [
                question.frame_evidence_id
                for question in output.wrong_questions
                if question.frame_evidence_id is not None
            ] + [
                figure.evidence_id
                for section in output.notes.sections
                for figure in section.figures
                if figure.evidence_id is not None
            ]
            gates["referenced_evidence_exists"] = all(ref in frame_ids for ref in references)
        return gates

    def mock_output(
        self, evidence: Sequence[Evidence], duration: float, item: EvalItem | None
    ) -> LessonOutput:
        sentences = _sentences(_transcript_text(evidence), 4) or ["模拟题目"]
        figures = _figures(evidence, duration, 2, "模拟图注：题目画面")
        frame = figures[0]
        question = WrongQuestion(
            stem=sentences[0],
            correct_answer="（模拟答案）",
            common_mistake="（模拟常见错误）",
            solution_steps=sentences[1:3],
            knowledge_points=["模拟知识点"],
            start_seconds=0.0,
            end_seconds=min(duration, 30.0),
            frame_timestamp_seconds=frame.timestamp_seconds,
            frame_evidence_id=frame.evidence_id,
        )
        notes = StudyNotes(
            title="模拟笔记",
            sections=[
                ArticleSection(heading=f"要点{index + 1}", body=text, figures=[figures[index]])
                for index, text in enumerate((sentences * 2)[:2])
            ],
            summary="模拟总结",
        )
        sources = [figure.timestamp_seconds for figure in figures]
        return LessonOutput(
            wrong_questions=[question],
            notes=notes,
            video=_mock_storyboard("模拟教学视频", sentences, sources),
        )

    def text(self, output: LessonOutput) -> str:
        parts: list[str] = []
        for question in output.wrong_questions:
            parts.extend(
                [
                    question.stem,
                    *question.options,
                    question.correct_answer,
                    question.common_mistake,
                    *question.solution_steps,
                    *question.knowledge_points,
                ]
            )
        parts.append(output.notes.title)
        parts.extend(_section_text(section) for section in output.notes.sections)
        parts.append(output.notes.summary)
        parts.append(_storyboard_text(output.video))
        return "\n".join(parts)

    def spans(self, output: LessonOutput) -> list[tuple[float, float]]:
        spans = [
            (question.frame_timestamp_seconds, question.frame_timestamp_seconds)
            for question in output.wrong_questions
        ]
        spans.extend(
            (figure.timestamp_seconds, figure.timestamp_seconds)
            for section in output.notes.sections
            for figure in section.figures
        )
        spans.extend(
            (time, time) for scene in output.video.scenes for time in scene.source_timestamps
        )
        return spans

    def timestamps(self, output: LessonOutput) -> list[float]:
        values = [time for time, _ in self.spans(output)]
        for question in output.wrong_questions:
            values.extend([question.start_seconds, question.end_seconds])
        return values

    def structure(self, output: LessonOutput, duration: float) -> dict[str, bool]:
        figures = [figure for section in output.notes.sections for figure in section.figures]
        checks = {
            "questions_complete": all(
                question.correct_answer
                and question.common_mistake
                and question.solution_steps
                and question.knowledge_points
                for question in output.wrong_questions
            ),
            "question_windows_valid": all(
                0 <= question.start_seconds <= question.frame_timestamp_seconds
                and question.frame_timestamp_seconds <= question.end_seconds <= duration + 0.5
                for question in output.wrong_questions
            ),
            "notes_sections_at_least_2": len(output.notes.sections) >= 2,
            "notes_figures_captioned": bool(figures)
            and all(len(figure.caption) >= 4 for figure in figures),
        }
        checks.update(
            {f"video_{key}": value for key, value in storyboard_checks(output.video).items()}
        )
        return checks


TASKS: dict[str, EvalTask[Any]] = {
    "t1": ArticleTask(),
    "t2a": ExplainerTask(),
    "t2b": ClipReviewTask(),
    "t3": LessonTask(),
}


def get_task(task_id: str) -> EvalTask[Any]:
    try:
        return TASKS[task_id]
    except KeyError:
        raise ValueError(f"unknown task: {task_id}") from None


def output_json(output: EvalOutput) -> str:
    return json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2)
