import json
from pathlib import Path

from app.services.planner_service import planner_service
from app.services.skill_registry_service import skill_registry


def test_skill_registry_exposes_p0_contracts():
    skills = {skill.name: skill for skill in skill_registry.list_skills()}

    expected = {
        "IngestVideo",
        "TranscribeAudio",
        "BuildTranscriptIndex",
        "SummarizeContent",
        "LocateContent",
        "GenerateNotes",
        "AnswerWithContext",
        "ExtractFrames",
    }

    assert expected.issubset(skills)
    for skill_name in expected:
        skill = skills[skill_name]
        assert skill.inputs_schema
        assert skill.outputs_schema
        assert skill.cost_estimate in {"low", "medium", "high"}
        assert skill.failure_modes
        assert skill.idempotency_key


def test_planner_eval_set_meets_p0_thresholds():
    eval_path = Path(__file__).resolve().parents[1] / "evals" / "planner_eval_set.json"
    cases = json.loads(eval_path.read_text(encoding="utf-8"))

    required_hits = 0
    forbidden_clean = 0
    artifact_hits = 0

    for case in cases:
        plan = planner_service.create_plan(case["query"])
        validation = skill_registry.validate_plan(plan)
        planned_skills = {step.skill for step in plan.steps}

        assert validation.valid, validation.errors
        if set(case["required_skills"]).issubset(planned_skills):
            required_hits += 1
        if not (set(case.get("forbidden_skills", [])) & planned_skills):
            forbidden_clean += 1
        if plan.artifact_type == case["expected_artifact"]:
            artifact_hits += 1

    total = len(cases)
    assert total >= 100
    assert required_hits / total >= 0.85
    assert 1 - (forbidden_clean / total) <= 0.15
    assert artifact_hits / total >= 0.85


def test_extract_frames_only_for_explicit_visual_requests():
    normal_plan = planner_service.create_plan("把这个课程整理成复习笔记")
    visual_plan = planner_service.create_plan("制作图文并茂的笔记")

    assert "ExtractFrames" not in {step.skill for step in normal_plan.steps}
    assert "ExtractFrames" in {step.skill for step in visual_plan.steps}
    assert visual_plan.requires_user_confirmation


def test_force_skills_supplements_extract_frames():
    # 普通摘要 query 默认不含 ExtractFrames
    base = planner_service.create_plan("总结这个视频")
    assert "ExtractFrames" not in {s.skill for s in base.steps}

    # 手动补充 ExtractFrames 后强制走带截帧的 notes 链路
    forced = planner_service.create_plan("总结这个视频", force_skills=["ExtractFrames"])
    assert forced.artifact_type == "notes"
    assert "ExtractFrames" in {s.skill for s in forced.steps}


def test_visual_mode_off_never_extracts_frames():
    # off：即便 query 含视觉词也不加任何图像 skill，且不被强制转成 notes
    plan = planner_service.create_plan("制作图文并茂的截图笔记", visual_mode="off")
    assert "ExtractFrames" not in {s.skill for s in plan.steps}
    assert plan.visual_mode == "off"
    assert not plan.requires_user_confirmation

    # 解除"视觉词强制转 notes"耦合：off 下"带截图的总结"仍是 summary，且不截帧
    plan2 = planner_service.create_plan("给我一个带截图的总结", visual_mode="off")
    assert plan2.artifact_type == "summary"
    assert "ExtractFrames" not in {s.skill for s in plan2.steps}


def test_visual_mode_on_forces_illustrated_notes():
    # on：即便纯文本总结 query，也强制走带截帧的 notes 链路
    plan = planner_service.create_plan("总结这个视频", visual_mode="on")
    assert plan.artifact_type == "notes"
    assert "ExtractFrames" in {s.skill for s in plan.steps}
    assert plan.visual_mode == "on"


def test_visual_mode_auto_matches_query_inference():
    # auto（默认）：保持既有行为——视觉词才截帧，否则不截，且与不传参一致（golden set 基线）
    visual = planner_service.create_plan("整理成图文笔记", visual_mode="auto")
    plain = planner_service.create_plan("总结这个视频", visual_mode="auto")
    assert "ExtractFrames" in {s.skill for s in visual.steps}
    assert "ExtractFrames" not in {s.skill for s in plain.steps}
    assert {s.skill for s in visual.steps} == {
        s.skill for s in planner_service.create_plan("整理成图文笔记").steps
    }
