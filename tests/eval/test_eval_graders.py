"""Deterministic graders, text matching and task schemas, on hand-written fixtures."""

from __future__ import annotations

from typing import Any

import pytest

from tests.eval.helpers import make_item
from vidsnap.contracts import Evidence
from vidsnap.eval.graders import grade_output, grade_questions
from vidsnap.eval.suite import ReferenceQuestion
from vidsnap.eval.tasks import (
    ArticleOutput,
    LessonOutput,
    StoryboardOutput,
    WrongQuestion,
    get_task,
    storyboard_checks,
)
from vidsnap.eval.text import (
    error_rate,
    matches,
    matches_math,
    normalize,
    parse_timestamp,
)


def article(**overrides: Any) -> ArticleOutput:
    payload: dict[str, Any] = {
        "title": "判别式与模型：一篇测试文章",
        "intro": "这是一段足够长的引言，用来介绍文章讲的内容和背景信息。",
        "takeaways": ["判别式决定根的个数", "Llama 3 8B 的维度", "第三条要点"],
        "sections": [
            {
                "heading": f"第{index}节",
                "body": "正文讲到判别式，以及屏幕上的数字。",
                "figures": [{"timestamp_seconds": time, "caption": "画面展示了公式和数字"}],
            }
            for index, time in enumerate((9.0, 25.0, 50.0), start=1)
        ],
        "summary": "总结：" + "这篇文章讲清楚了判别式，并给出了例子。" * 3,
    }
    payload.update(overrides)
    return ArticleOutput.model_validate(payload)


def test_normalize_and_keyword_groups() -> None:
    text = normalize("Llama-3 8B，隐藏维度 4096。")
    assert text == "llama38b隐藏维度4096"
    assert matches(text, [["llama"], ["4096", "四千"]])
    assert not matches(text, [["llama"], ["2048"]])


def test_math_matching_keeps_signs() -> None:
    assert matches_math("x = 2 或 x = 3", [["x=2"]])
    assert not matches_math("x = −2 或 x = −3", [["x=2"]])
    assert matches_math("x²−5x+6=0", [["x2-5x+6"]])
    assert matches_math("x ≠ 1", [["x≠1"]])


def test_error_rates() -> None:
    assert error_rate("今天讲判别式", "今天讲判别式", "zh") == (0.0, False)
    rate, _ = error_rate("今天将判别式", "今天讲判别式", "zh")
    assert rate == pytest.approx(1 / 6, abs=1e-3)
    rate, _ = error_rate("we met twice a year", "we meet twice a year", "en")
    assert rate == pytest.approx(0.2)


def test_timestamps_accept_clock_strings() -> None:
    assert parse_timestamp("01:30") == 90.0
    assert parse_timestamp("1:02:03") == 3723.0
    assert parse_timestamp("12.5s") == 12.5
    figure_output = article(
        sections=[
            {
                "heading": "h",
                "body": "b",
                "figures": [{"timestamp_seconds": "00:10", "caption": "图注说明画面"}],
            }
        ]
    )
    assert figure_output.sections[0].figures[0].timestamp_seconds == 10.0


def test_outputs_ignore_unknown_fields() -> None:
    output = ArticleOutput.model_validate({**article().model_dump(), "extra": "ignored"})
    assert not hasattr(output, "extra")


def test_good_article_scores_coverage_moments_and_entities() -> None:
    item = make_item()
    task = get_task("t1")
    good = article(intro="引言提到 Llama 3 8B 和判别式，以及屏幕上的数字 3.35，这些都要准确。")
    metrics = grade_output(task, good, item, 60.0)
    assert metrics["success"] is True
    assert metrics["key_point_coverage"] == 1.0
    assert metrics["entity_recall"] == 1.0
    assert metrics["moment_recall"] == 1.0
    assert metrics["hallucinations"] == 0
    assert metrics["timestamps_out_of_range"] == 0.0
    assert isinstance(metrics["primary"], float)


def test_misses_hallucinations_and_out_of_range_timestamps() -> None:
    item = make_item()
    bad = article(
        intro="这篇引言写的是计算受限的 Decode，没有提到任何参考要点，只是凑够长度而已。",
        sections=[
            {
                "heading": "h",
                "body": "b",
                "figures": [{"timestamp_seconds": 500, "caption": "错误时间的画面"}],
            }
        ],
    )
    metrics = grade_output(get_task("t1"), bad, item, 60.0)
    assert metrics["missed_key_points"] == ["kp-b"] or "kp-b" in metrics["missed_key_points"]
    assert metrics["hallucinations"] == 1
    assert metrics["moment_recall"] == 0.0
    assert metrics["timestamps_out_of_range"] == 1.0
    assert metrics["structure_checks"]["figures_at_least_3"] is False


def test_failed_run_scores_zero_primary_only_with_reference() -> None:
    assert grade_output(get_task("t1"), None, make_item(), 60.0)["primary"] == 0.0
    unreferenced = make_item(reference={})
    assert grade_output(get_task("t1"), None, unreferenced, 60.0)["primary"] is None


def wrong_question(stem: str, answer: str, mistake: str, frame: float) -> WrongQuestion:
    return WrongQuestion(
        stem=stem,
        correct_answer=answer,
        common_mistake=mistake,
        solution_steps=["代回验算"],
        knowledge_points=["因式分解"],
        start_seconds=0,
        end_seconds=60,
        frame_timestamp_seconds=frame,
    )


def test_question_grading_checks_answer_sign_and_time() -> None:
    reference = [
        ReferenceQuestion(
            id="q3",
            stem="解方程",
            stem_match=[["x2-5x+6"]],
            answer="x=2或x=3",
            answer_match=[["x=2", "2或3"]],
            mistake="符号写反",
            mistake_match=[["符号"], ["反", "错"]],
            window=(10, 40),
        )
    ]
    right = grade_questions(
        reference, [wrong_question("解方程 x²-5x+6=0", "x=2 或 x=3", "因式分解符号写反", 20)]
    )
    assert right["question_recall"] == 1.0
    assert right["answer_accuracy"] == 1.0
    assert right["mistake_coverage"] == 1.0
    assert right["question_time_accuracy"] == 1.0
    wrong = grade_questions(
        reference,
        [
            wrong_question("解方程 x^2 - 5x + 6 = 0", "x=-2 或 x=-3", "粗心", 90),
            wrong_question("另一道编造的题", "1", "无", 5),
        ],
    )
    assert wrong["question_recall"] == 1.0
    assert wrong["answer_accuracy"] == 0.0
    assert wrong["mistake_coverage"] == 0.0
    assert wrong["question_time_accuracy"] == 0.0
    assert wrong["question_precision"] == 0.5


def test_harness_gates_require_cited_frames() -> None:
    task = get_task("t1")
    frame = Evidence(id="frame-001", start_seconds=9, end_seconds=9, modality="frame")
    cited = article(
        sections=[
            {
                "heading": "h",
                "body": "b",
                "figures": [
                    {"timestamp_seconds": 9, "caption": "画面", "evidence_id": "frame-001"}
                ],
            }
        ]
    )
    assert task.gates(cited, [frame], 60, harness=True)["referenced_evidence_exists"]
    uncited = article()
    assert not task.gates(uncited, [frame], 60, harness=True)["referenced_evidence_exists"]
    assert "referenced_evidence_exists" not in task.gates(uncited, [], 60, harness=False)


def test_storyboard_rules() -> None:
    good = StoryboardOutput.model_validate(
        {
            "title": "t",
            "scenes": [
                {
                    "title": f"s{index}",
                    "start_seconds": index * 12,
                    "end_seconds": index * 12 + 12,
                    "captions": [
                        {
                            "start_seconds": index * 12 + 1,
                            "end_seconds": index * 12 + 5,
                            "text": "字幕",
                        }
                    ],
                }
                for index in range(3)
            ],
        }
    )
    assert all(storyboard_checks(good).values())
    bad = good.model_copy(deep=True)
    bad.scenes[0].captions[0].end_seconds = 11.5
    bad.scenes[0].captions[0].text = "很长" * 30
    checks = storyboard_checks(bad)
    assert not checks["captions_at_most_6s"]
    assert not checks["captions_short"]


@pytest.mark.parametrize("task_id", ["t1", "t2a", "t2b", "t3"])
def test_mock_outputs_are_schema_valid_and_prompts_carry_inputs(task_id: str) -> None:
    task = get_task(task_id)
    item = make_item(inputs={"goal": "具体目标", "topic": "某个主题", "audience": "初中生"})
    evidence = [
        Evidence(
            id="transcript-001",
            start_seconds=0,
            end_seconds=60,
            modality="transcript",
            content="第一句。第二句。",
        ),
        Evidence(id="frame-001", start_seconds=12, end_seconds=12, modality="frame"),
    ]
    output = task.mock_output(evidence, 60.0, item)
    assert task.parse(output.model_dump(mode="json")) == output
    assert all(task.gates(output, evidence, 60.0, harness=True).values())
    prompt = task.instructions(item, harness=True)
    assert "具体目标" in prompt and "某个主题" in prompt and "evidence_id" in prompt
    native = task.instructions(item, harness=False)
    assert "完整的视频" in native and "evidence" not in native.split("JSON 结构如下")[0]
    if task_id == "t3":
        assert isinstance(output, LessonOutput)


@pytest.mark.parametrize(
    ("answer", "chosen"),
    [
        ("C", True),
        ("C. have lived", True),
        ("选 C", True),
        ("答案：C", True),
        ("（C）没有实数根", True),
        ("Cl2", False),
        ("B", False),
        ("x = 2", False),
    ],
)
def test_multiple_choice_answers_accept_the_option_letter(answer: str, chosen: bool) -> None:
    from vidsnap.eval.graders import option_chosen

    assert option_chosen(answer, "C") is chosen
    reference = [
        ReferenceQuestion(
            id="q5",
            stem="几个实数根",
            stem_match=[["实数根"]],
            answer="没有实数根，选 C",
            answer_match=[["没有实数根"]],
            answer_option="C",
            mistake="漏掉 4",
            mistake_match=[["4"]],
            window=(0, 30),
        )
    ]
    graded = grade_questions(reference, [wrong_question("有几个实数根", answer, "漏掉4", 10)])
    assert graded["answer_accuracy"] == (1.0 if chosen else 0.0)
