"""计算 planner golden set 通过率，输出 shields.io endpoint JSON（README 公开成绩单徽章）。

严格口径：一条 case 必须同时满足 required_skills 全命中、forbidden_skills 零命中、
artifact_type 完全一致、plan 校验通过，才算通过——比测试的分项阈值更苛刻，
因为成绩单的意义就是敢公开最严的那个数。

用法: python scripts/compute_planner_score.py <输出文件路径>
（JSON 写文件而非 stdout，避免 config 加载时的提示文本污染输出。）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.planner_service import planner_service  # noqa: E402
from app.services.skill_registry_service import skill_registry  # noqa: E402


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("planner-evals.json")
    eval_path = Path(__file__).resolve().parents[1] / "app" / "evals" / "planner_eval_set.json"
    cases = json.loads(eval_path.read_text(encoding="utf-8"))

    passed = 0
    for case in cases:
        plan = planner_service.create_plan(case["query"])
        planned = {step.skill for step in plan.steps}
        ok = (
            skill_registry.validate_plan(plan).valid
            and set(case["required_skills"]).issubset(planned)
            and not (set(case.get("forbidden_skills", [])) & planned)
            and plan.artifact_type == case["expected_artifact"]
        )
        passed += int(ok)

    total = len(cases)
    ratio = passed / total if total else 0.0
    color = (
        "brightgreen" if ratio >= 0.9
        else "green" if ratio >= 0.85
        else "yellow" if ratio >= 0.7
        else "red"
    )
    badge = {
        "schemaVersion": 1,
        "label": "planner evals",
        "message": f"{passed}/{total} ({ratio:.0%})",
        "color": color,
    }
    out_path.write_text(json.dumps(badge, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stderr.write(f"planner evals: {passed}/{total} ({ratio:.0%}) -> {out_path}\n")


if __name__ == "__main__":
    main()
