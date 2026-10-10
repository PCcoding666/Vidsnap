"""Offline end-to-end runs: every suite through the kernel, traces, index, report, review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from tests.ansi import strip_ansi
from tests.eval.helpers import SUITES_DIR, committed_suite, item_payload, price_table, write_suite
from vidsnap.cli import app
from vidsnap.eval.costs import load_eval_prices
from vidsnap.eval.report import build_report, load_results
from vidsnap.eval.review import build_review, import_scores
from vidsnap.eval.runner import RunOptions, run_suite
from vidsnap.eval.suite import load_suite
from vidsnap.eval.systems import BuildOptions, parse_system
from vidsnap.trace.run_index import read_index

TASKS = ("t1", "t2a", "t2b", "t3")
FAKE_KEY = "fake-eval-credential-for-leak-test"


def events(bundle: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (bundle / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize("task", TASKS)
@pytest.mark.parametrize("system", ["harness+mock", "native:mock"])
def test_cli_mock_run_of_each_suite(task: str, system: str, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "eval",
            "run",
            "--suite",
            task,
            "--suites-dir",
            str(SUITES_DIR),
            "--system",
            system,
            "--media-mode",
            "fake",
            "--runs-root",
            str(tmp_path / "run"),
            "--out",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    document = json.loads(Path(summary["results"]).read_text(encoding="utf-8"))
    assert document["schema_version"] == "vidsnap.eval-result/v1"
    assert document["system"] == system and document["task"] == task
    ran = [item for item in document["items"] if "skipped" not in item]
    skipped = [item for item in document["items"] if "skipped" in item]
    assert ran and all(item["skipped"] == "placeholder" for item in skipped)
    index = read_index((tmp_path / "run").resolve())
    assert len([r for r in index.records if r["record"] == "run"]) == len(ran)
    for item in ran:
        assert item["terminal_state"] == "SUCCEEDED", item
        assert item["machine"]["success"] is True
        bundle = Path(item["bundle_path"])
        header = next(e for e in events(bundle) if e.get("event_type") == "run.started")
        assert header["payload"]["recipe"] == {
            "id": f"eval/{task}",
            "version": "eval-prompts/2026-10-10",
        }
        assert header["payload"]["policy"] == (
            "FixedPolicy" if system.startswith("harness") else "NativePolicy"
        )
        assert (Path(item["render"]["dir"]) / "output.json").is_file()
        if system.startswith("harness"):
            names = [
                e["payload"].get("name")
                for e in events(bundle)
                if e.get("event_type") == "tool.call.started"
            ]
            assert names == ["transcribe_audio", "sample_evidence"]
            assert item["stages"]["frames_sampled"] == 8
        else:
            types = {e.get("event_type") for e in events(bundle)}
            assert "tool.call.started" not in types
            assert "model.request.completed" in types


def mock_options(tmp_path: Path, task: str, system: str, **overrides: Any) -> RunOptions:
    options = RunOptions(
        suite=committed_suite(task),
        system=parse_system(system),
        media_root=tmp_path / "media",
        runs_root=tmp_path / "run",
        out_dir=tmp_path / "out",
        media_mode="fake",
    )
    for key, value in overrides.items():
        setattr(options, key, value)
    return options


@pytest.mark.asyncio
async def test_report_and_blind_review_round_trip(tmp_path: Path) -> None:
    harness_path, _ = await run_suite(mock_options(tmp_path, "t3", "harness+mock"))
    native_path, _ = await run_suite(mock_options(tmp_path, "t3", "native:mock"))
    documents = load_results([harness_path, native_path])
    report = build_report(documents)
    assert "## t3 (t3)" in report and "harness+mock" in report and "native:mock" in report
    assert "Per-stage metrics" in report and "lost: asr" in report
    assert "mock runs check plumbing only" in report

    page, key_path = tmp_path / "review.html", tmp_path / "key.json"
    pairs, review_id = build_review(documents[0], documents[1], page, key_path, seed=3)
    assert pairs == 5
    html_text = page.read_text(encoding="utf-8")
    assert "harness+mock" not in html_text and "native:mock" not in html_text
    assert "错题提取" in html_text and review_id in html_text
    key = json.loads(key_path.read_text(encoding="utf-8"))
    pair_ids = list(key["pairs"])
    scores = {
        "schema_version": "vidsnap.eval-review-scores/v1",
        "review_id": review_id,
        "suite_id": "t3",
        "pairs": [
            {
                "pair_id": pair_id,
                "dimensions": {"A": {"questions": 5, "notes": 4}, "B": {"questions": 2}},
                "preference": "A",
                "edit_minutes": {"A": 5, "B": None},
                "note": None,
            }
            for pair_id in pair_ids
        ],
    }
    human = import_scores(scores, key)
    assert len(human.scores) == 2 * len(pair_ids)
    for score in human.scores:
        side = "A" if score.preferred else "B"
        assert (
            key["pairs"][next(p for p in pair_ids if key["pairs"][p]["item_id"] == score.item_id)][
                side
            ]["system"]
            == score.system
        )
    report_with_humans = build_report(documents, human.scores)
    assert "Preferred" in report_with_humans


@pytest.mark.asyncio
async def test_live_system_without_key_is_blocked_and_stops_the_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("VIDSNAP_DASHSCOPE_API_KEY", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    media = tmp_path / "media" / "public"
    media.mkdir(parents=True)
    (media / "x.mp4").write_bytes(b"tiny local stand-in for a video")
    first = item_payload(item_id="x-01")
    second = item_payload(item_id="x-02")
    for payload in (first, second):
        payload["source"]["sha256"] = None
        payload["source"]["kind"] = "synthetic"
        payload["source"]["generator"] = None
    suite_path = write_suite(tmp_path / "t2b.json", "t2b", [first, second])
    prices = load_eval_prices(price_table(tmp_path / "prices.json"))

    from vidsnap.eval.adapters import FakeMedia

    options = RunOptions(
        suite=load_suite(suite_path),
        system=parse_system("native:qwen3.8-omni-flash"),
        media_root=tmp_path / "media",
        runs_root=tmp_path / "run",
        out_dir=tmp_path / "out",
        prices=prices,
        max_cost=1.0,
        media_factory=lambda item, duration: FakeMedia(duration_seconds=60, has_audio=True),
    )
    _, document = await run_suite(options)
    first_record, second_record = document["items"]
    assert first_record["terminal_state"] == "BLOCKED"
    assert first_record["failure_category"] == "provider_unavailable"
    assert first_record["machine"]["primary"] == 0.0
    assert first_record["cost"]["amount"] is None
    assert document["stopped_reason"] == "cost_unknown"
    assert second_record == {"item_id": "x-02", "item_status": "ready", "skipped": "cost_unknown"}


@pytest.mark.asyncio
async def test_live_harness_path_is_traced_priced_and_never_leaks_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDSNAP_DASHSCOPE_API_KEY", FAKE_KEY)
    task_outputs: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        body = json.loads(request.content)
        if body["model"] == "qwen3-asr-flash":
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "评审时间增加了百分之三十"}}]}
            )
        task_outputs["system"] = body["messages"][0]["content"]
        output = {
            "summary": "嘉宾认为不会取代初级工程师，评审时间增加了 30%。" * 4,
            "claims": [
                {
                    "text": "评审时间增加 30%",
                    "start_seconds": 5,
                    "end_seconds": 20,
                    "evidence_ids": ["transcript-001"],
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 2000, "completion_tokens": 300},
            },
        )

    prices = load_eval_prices(price_table(tmp_path / "prices.json"))
    options = mock_options(
        tmp_path,
        "t2b",
        "harness+qwen3.8-max",
        item_ids=("t2b-syn-01",),
        prices=prices,
        max_cost=1.0,
        build=BuildOptions(transport=httpx.MockTransport(handler)),
    )
    path, document = await run_suite(options)
    record = document["items"][0]
    assert record["terminal_state"] == "SUCCEEDED", record
    assert "evidence" in task_outputs["system"] or "证据" in task_outputs["system"]
    cost = record["cost"]
    expected_model = (2000 * 12 + 300 * 36) / 1_000_000
    assert cost["model_amount"] == pytest.approx(expected_model)
    assert cost["speech_seconds"] == pytest.approx(79.0)
    assert cost["amount"] == pytest.approx(expected_model + 79.0 * 0.00022)
    assert document["spent"] == pytest.approx(cost["amount"])
    assert record["machine"]["key_point_coverage"] == pytest.approx(0.5)
    assert record["stages"]["losses"]["lost_at_asr"] == 2
    assert record["stages"]["asr_upload_bytes"] > 0
    assert record["stages"]["model_request_bytes"] > 0
    header = next(
        e for e in events(Path(record["bundle_path"])) if e.get("event_type") == "run.started"
    )
    assert header["payload"]["provider"] == {"id": "qwen", "model": "qwen3.8-max"}
    assert header["payload"]["speech_recognizer"] == {"id": "qwen", "model": "qwen3-asr-flash"}
    for file in [path, *Path(record["bundle_path"]).rglob("*"), *(tmp_path / "run").rglob("*")]:
        if file.is_file():
            assert FAKE_KEY not in file.read_bytes().decode("utf-8", errors="replace")


def test_cli_refuses_live_runs_without_a_budget_and_fake_media_for_live(tmp_path: Path) -> None:
    runner = CliRunner()
    base = ["eval", "run", "--suite", "t1", "--suites-dir", str(SUITES_DIR)]
    no_budget = runner.invoke(app, [*base, "--system", "native:qwen3.8-omni-flash"])
    assert no_budget.exit_code == 2 and "--max-cost" in no_budget.output
    fake_live = runner.invoke(
        app, [*base, "--system", "harness+qwen3.8-max", "--media-mode", "fake"]
    )
    assert fake_live.exit_code == 2
    unknown = runner.invoke(app, [*base, "--system", "native:gpt-x"])
    assert unknown.exit_code == 2 and "allow-listed" in unknown.output


def test_cli_help_validate_and_systems() -> None:
    runner = CliRunner()
    help_text = strip_ansi(runner.invoke(app, ["--help"]).stdout)
    assert "eval" in help_text
    systems = runner.invoke(app, ["eval", "systems"])
    assert "native:qwen3.8-omni-flash" in systems.stdout and "harness+qwen3.8-max" in systems.stdout
    validate = runner.invoke(
        app, ["eval", "validate", "t3", "--suites-dir", str(SUITES_DIR), "--no-hashes"]
    )
    assert "t3 (t3): 6 items" in validate.stdout


@pytest.mark.asyncio
async def test_regrade_recomputes_from_bundles_without_model_calls(tmp_path: Path) -> None:
    from vidsnap.eval.runner import regrade_document

    path, document = await run_suite(mock_options(tmp_path, "t2b", "harness+mock"))
    stored = json.loads(path.read_text(encoding="utf-8"))
    for record in stored["items"]:
        if "skipped" not in record:
            record["machine"] = {}
            record["stages"] = {}
    regraded = regrade_document(stored, committed_suite("t2b"), None)
    original = {r["item_id"]: r for r in document["items"] if "skipped" not in r}
    for record in regraded["items"]:
        if "skipped" in record:
            continue
        assert record["machine"]["primary"] == original[record["item_id"]]["machine"]["primary"]
        assert record["stages"]["model_request_bytes"] >= 0
        assert record["stages"]["asr_upload_bytes"] == 0  # mock recognizer uploads nothing
    assert "regraded_at" in regraded
