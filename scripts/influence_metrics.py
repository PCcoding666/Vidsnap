#!/usr/bin/env python3
"""影响力指标快照(glass-box:数据公开进仓库)。

采集:stars / forks / watchers / open issues + 最近 14 天 views/clones + 热门来源,
追加一行 JSON 到 docs/metrics/influence.jsonl,并打印人类可读摘要。
为"影响力周会"供数:看斜率,不看绝对值。

用法: python3 scripts/influence_metrics.py [--repo owner/name]
前置: gh 已登录且对仓库有 push 权限(traffic API 要求)。
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO = (
    sys.argv[sys.argv.index("--repo") + 1]
    if "--repo" in sys.argv
    else "PCcoding666/Vidsnap"
)


def gh(path: str):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"warn: gh api {path} failed: {r.stderr.strip()[:120]}\n")
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def main() -> None:
    repo = gh(f"repos/{REPO}") or {}
    views = gh(f"repos/{REPO}/traffic/views") or {}
    clones = gh(f"repos/{REPO}/traffic/clones") or {}
    referrers = gh(f"repos/{REPO}/traffic/popular/referrers") or []

    snap = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "watchers": repo.get("subscribers_count"),
        "open_issues": repo.get("open_issues_count"),
        "views_14d": views.get("count"),
        "views_uniques_14d": views.get("uniques"),
        "clones_14d": clones.get("count"),
        "clones_uniques_14d": clones.get("uniques"),
        "top_referrers": [
            {"ref": r.get("referrer"), "uniques": r.get("uniques")}
            for r in (referrers or [])[:5]
        ],
    }

    out = Path(__file__).resolve().parents[1] / "docs" / "metrics" / "influence.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")

    print(f"⭐ stars={snap['stars']}  forks={snap['forks']}  watchers={snap['watchers']}  issues={snap['open_issues']}")
    print(f"👀 views(14d)={snap['views_14d']} (uniques {snap['views_uniques_14d']})   clones(14d)={snap['clones_14d']} (uniques {snap['clones_uniques_14d']})")
    print(f"🔗 top referrers: {snap['top_referrers'] or '(none yet)'}")
    print(f"→ appended to {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")


if __name__ == "__main__":
    main()
