"""Deterministic machine graders: coverage, entities, hallucinations, timing, structure.

No model judges another model here. Every metric is a string or timestamp check
against the item's reference; metrics whose reference is missing are ``None``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from statistics import mean
from typing import Any

from pydantic import JsonValue

from vidsnap.eval.suite import EvalItem, KeyMoment, KeyPoint, ReferenceQuestion
from vidsnap.eval.tasks import EvalOutput, EvalTask, LessonOutput, WrongQuestion
from vidsnap.eval.text import matches, matches_math, normalize

_QUESTION_TIME_TOLERANCE = 5.0
_EDGE = 0.5


def key_point_hits(points: Sequence[KeyPoint], normalized_text: str) -> dict[str, bool]:
    return {point.id: matches(normalized_text, point.match) for point in points}


def weighted_coverage(points: Sequence[KeyPoint], hits: dict[str, bool]) -> float | None:
    total = sum(point.weight for point in points)
    if not points or total <= 0:
        return None
    return round(sum(point.weight for point in points if hits.get(point.id)) / total, 4)


def moment_hits(
    moments: Sequence[KeyMoment], spans: Sequence[tuple[float, float]]
) -> dict[str, bool]:
    return {
        moment.id: any(
            start - moment.tolerance_seconds <= moment.at_seconds <= end + moment.tolerance_seconds
            for start, end in spans
        )
        for moment in moments
    }


def _ratio(hits: dict[str, bool]) -> float | None:
    if not hits:
        return None
    return round(sum(1 for hit in hits.values() if hit) / len(hits), 4)


def option_chosen(answer: str, option: str) -> bool:
    """True when a multiple-choice answer names ``option`` (``C``, ``C.``, ``选 C`` ...)."""
    text = unicodedata.normalize("NFKC", answer).strip().upper()
    pattern = rf"^(选|答案)?\s*[:：]?\s*[(（]?{option}([)）.、:：,，\s]|$)|选\s*{option}(?![A-Z])"
    return re.search(pattern, text) is not None


def _question_text(question: WrongQuestion) -> str:
    return "\n".join([question.stem, *question.options])


def grade_questions(
    references: Sequence[ReferenceQuestion], predicted: Sequence[WrongQuestion]
) -> dict[str, JsonValue]:
    """Match reference wrong questions by stem keywords, then check each match."""
    if not references:
        return {}
    unused = list(range(len(predicted)))
    matched = 0
    answers = 0
    mistakes = 0
    timed = 0
    per_question: dict[str, JsonValue] = {}
    for reference in references:
        index = next(
            (i for i in unused if matches_math(_question_text(predicted[i]), reference.stem_match)),
            None,
        )
        if index is None:
            per_question[reference.id] = {"found": False}
            continue
        unused.remove(index)
        question = predicted[index]
        matched += 1
        answer_ok = matches_math(question.correct_answer, reference.answer_match) or (
            reference.answer_option is not None
            and option_chosen(question.correct_answer, reference.answer_option)
        )
        mistake_text = "\n".join([question.common_mistake, *question.solution_steps])
        mistake_ok = matches_math(mistake_text, reference.mistake_match)
        start, end = reference.window
        time_ok = (
            start - _QUESTION_TIME_TOLERANCE
            <= question.frame_timestamp_seconds
            <= end + _QUESTION_TIME_TOLERANCE
        )
        answers += answer_ok
        mistakes += mistake_ok
        timed += time_ok
        per_question[reference.id] = {
            "found": True,
            "answer": answer_ok,
            "mistake": mistake_ok,
            "time": time_ok,
        }
    total = len(references)
    return {
        "question_recall": round(matched / total, 4),
        "answer_accuracy": round(answers / total, 4),
        "mistake_coverage": round(mistakes / total, 4),
        "question_time_accuracy": round(timed / total, 4),
        "question_precision": round(matched / len(predicted), 4) if predicted else 0.0,
        "questions": per_question,
    }


def grade_output(
    task: EvalTask[Any], output: EvalOutput | None, item: EvalItem, duration: float
) -> dict[str, JsonValue]:
    """All machine metrics for one item; failures score 0 on the primary metric."""
    reference = item.reference
    has_reference = bool(reference.key_points or reference.questions)
    if output is None:
        return {
            "success": False,
            "primary": 0.0 if has_reference else None,
            "has_reference": has_reference,
        }
    normalized = normalize(task.text(output))
    point_hits = key_point_hits(reference.key_points, normalized)
    spans = task.spans(output)
    stamps = task.timestamps(output)
    moments = moment_hits(reference.key_moments, spans)
    entity_hits = {entity: normalize(entity) in normalized for entity in reference.entities}
    forbidden = [
        statement.id for statement in reference.forbidden if matches(normalized, statement.match)
    ]
    structure = task.structure(output, duration)
    out_of_range = [value for value in stamps if not -_EDGE <= value <= duration + _EDGE]
    metrics: dict[str, JsonValue] = {
        "success": True,
        "has_reference": has_reference,
        "key_point_coverage": weighted_coverage(reference.key_points, point_hits),
        "missed_key_points": [point_id for point_id, hit in point_hits.items() if not hit],
        "entity_recall": _ratio(entity_hits),
        "hallucinations": len(forbidden) if reference.forbidden else None,
        "hallucinated": list(forbidden),
        "moment_recall": _ratio(moments),
        "missed_moments": [moment_id for moment_id, hit in moments.items() if not hit],
        "timestamps_out_of_range": round(len(out_of_range) / len(stamps), 4) if stamps else None,
        "structure": round(mean(1.0 if ok else 0.0 for ok in structure.values()), 4)
        if structure
        else None,
        "structure_checks": dict(structure),
    }
    if isinstance(output, LessonOutput):
        metrics.update(grade_questions(reference.questions, output.wrong_questions))
    metrics["primary"] = primary_score(task.task_id, metrics) if has_reference else None
    return metrics


def _number(value: JsonValue) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def primary_score(task_id: str, metrics: dict[str, JsonValue]) -> float | None:
    """Mean of the task's headline metrics that could be computed."""
    names = (
        (
            "question_recall",
            "answer_accuracy",
            "mistake_coverage",
            "key_point_coverage",
            "structure",
        )
        if task_id == "t3"
        else ("key_point_coverage", "moment_recall", "structure")
    )
    values = [number for name in names if (number := _number(metrics.get(name))) is not None]
    return round(mean(values), 4) if values else None
