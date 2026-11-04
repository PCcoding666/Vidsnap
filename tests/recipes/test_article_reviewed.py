"""Offline regression tests for the opt-in reviewed article workflow."""

import asyncio
import json
from copy import deepcopy

import pytest

from tests.plugins.test_builtin_tools import FakeWindowMedia, make_context
from vidsnap.contracts import (
    HarnessPolicy,
    ProviderUsage,
    TerminalState,
    VideoSource,
    default_loop_spec,
)
from vidsnap.eval.adapters import FakeMedia, HarnessEvalAdapter
from vidsnap.eval.providers import Completion, MockSynthesis
from vidsnap.eval.suite import EvalItem, ItemInputs, SourceVideo
from vidsnap.eval.tasks import get_task
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.plugins.builtin.sample_evidence import DenseSampleEvidencePlugin, SampleEvidenceArgs
from vidsnap.providers.base import ProviderError
from vidsnap.recipes.article import ArticleRecipeRunner
from vidsnap.runtime import HarnessKernel, RunContext, default_plugin_registry
from vidsnap.video.sampling import AdaptiveSampler


@pytest.mark.asyncio
async def test_dense_windows_do_not_depend_on_global_candidates(tmp_path):
    media = FakeWindowMedia()  # No global candidates between 2 and 3 seconds.
    context = make_context(tmp_path, media=media, recognizer=None)
    result = await DenseSampleEvidencePlugin().execute(
        SampleEvidenceArgs(windows=[{"start_seconds": 2, "end_seconds": 3}], max_frames=4),
        context,
    )
    assert len(result.evidence_ids) == 4
    assert len(set(media.sampled_timestamps)) == 4
    assert all(2 < time < 3 for time in media.sampled_timestamps)


def run_context(tmp_path, *, max_calls=2):
    item = EvalItem(
        item_id="review-test",
        status="needs_reference",
        source=SourceVideo(kind="owner", licence="synthetic", language="zh"),
        inputs=ItemInputs(goal="Write an illustrated article"),
    )
    return RunContext(
        source=VideoSource(path=tmp_path / "synthetic.mp4"),
        policy=HarnessPolicy(max_model_calls=max_calls),
        bundle=RunBundle.create(
            tmp_path / "run", loop_spec=default_loop_spec(), provider_url="offline://mock"
        ),
        task_adapter=HarnessEvalAdapter(get_task("t1"), item),
        task_model=MockSynthesis(),
        media=FakeMedia(duration_seconds=120, has_audio=False),
        sampler=AdaptiveSampler(),
    )


class CountingStep:
    def __init__(self):
        self.calls = 0

    async def request(self, model):
        self.calls += 1
        return self.calls, ProviderUsage(
            model_calls=1, input_tokens=7, output_tokens=3, reported=True
        )


@pytest.mark.asyncio
async def test_model_steps_share_call_budget_and_record_usage(tmp_path):
    step = CountingStep()

    class Policy:
        async def execute(self, context, kernel):
            assert await kernel.run_model_step(context, step, phase="article_review") == 1
            await kernel.run_model_step(context, step, phase="article_patch")

    context = run_context(tmp_path, max_calls=1)
    result = await HarnessKernel(policy=Policy(), registry=default_plugin_registry()).run(context)
    assert result.terminal_state is TerminalState.EXHAUSTED
    assert step.calls == context.model_calls == 1
    events = [
        json.loads(line) for line in (result.run_path / "events.jsonl").read_text().splitlines()
    ]
    assert any(e.get("usage", {}).get("input_tokens") == 7 for e in events if e.get("usage"))


@pytest.mark.asyncio
async def test_model_step_deadline_cancels_work(tmp_path):
    cancelled = False

    class SlowStep:
        async def request(self, model):
            nonlocal cancelled
            try:
                await asyncio.Event().wait()
            finally:
                cancelled = True

    class Policy:
        async def execute(self, context, kernel):
            await kernel.run_model_step(context, SlowStep(), phase="article_review")

    # Virtual clock leaves 1 ms of the declared run budget; no real one-second sleep.
    times = iter([0.0, 899.999, 899.999])
    context = run_context(tmp_path)
    result = await HarnessKernel(
        policy=Policy(), registry=default_plugin_registry(), clock=lambda: next(times, 899.999)
    ).run(context)
    assert result.terminal_state is TerminalState.EXHAUSTED
    assert cancelled
    assert context.model_calls == 1


def draft_article():
    return {
        "title": "把视频变成可执行的教程",
        "intro": "根据视频里的操作过程整理。",
        "takeaways": ["先准备", "再连接", "最后验证"],
        "summary": "逐步验证结果。",
        "sections": [
            {
                "heading": f"步骤 {i}",
                "body": f"保留的正文 {i}",
                "figures": [
                    {
                        "timestamp_seconds": 7.5 + 15 * i,
                        "caption": "已完成并验证工作流",
                        "evidence_id": f"frame-{i + 1:03d}",
                    }
                ],
            }
            for i in range(3)
        ],
    }


def review_payload(*, failed=False, editorial=False):
    return {
        "schema_version": "vidsnap.article-review/v1",
        "figures": [
            {
                "section_index": i,
                "figure_index": 0,
                "evidence_id": f"frame-{i + 1:03d}",
                "verdict": "insufficient" if failed and i == 0 else "supported",
                "reason": "画面显示的是配置步骤",
            }
            for i in range(3)
        ],
        "issues": [{"section_index": 0, "reason": "正文重复，需要缩短"}] if editorial else [],
    }


def section_patch():
    section = deepcopy(draft_article()["sections"][0])
    section["body"] = "修订后的正文"
    section["figures"][0]["caption"] = "工作流配置页面"
    return {
        "schema_version": "vidsnap.article-patch/v1",
        "sections": [{"section_index": 0, "section": section}],
    }


class ScriptedSynthesis(MockSynthesis):
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def synthesize(self, request):
        self.requests.append(request)
        assert self.responses, "unexpected extra model call"
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return Completion(payload=response, usage=ProviderUsage(model_calls=1, reported=False))


async def run_reviewed(tmp_path, model, media=None):
    video = tmp_path / "synthetic.mp4"
    video.write_bytes(b"synthetic input, no real media")
    runner = ArticleRecipeRunner(
        system="harness+mock",
        recipe_version="v2",
        synthesis_port=model,
        media=media or FakeMedia(duration_seconds=120, has_audio=False),
    )
    return await runner.run(video, "改写成图文文章", tmp_path / "out", run_dir=tmp_path / "run")


@pytest.mark.asyncio
async def test_v2_reviews_actual_images_then_patches_only_flagged_section(tmp_path):
    model = ScriptedSynthesis(
        draft_article(), review_payload(failed=True), section_patch(), review_payload()
    )
    result = await run_reviewed(tmp_path, model)
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert len(model.requests) == 4
    assert [part["type"] for part in model.requests[1].content].count("image_url") == 3
    assert len([e for e in model.requests[2].evidence if e.modality == "frame"]) == 32  # 8 + 24
    output = json.loads((result.run_path / "result.json").read_text())
    assert output["sections"][0]["body"] == "修订后的正文"
    assert output["sections"][1:] == draft_article()["sections"][1:]
    assert output["title"] == draft_article()["title"]
    artifacts = result.run_path / "artifacts" / "article-v2"
    assert json.loads((artifacts / "draft.json").read_text()) == draft_article()
    assert (artifacts / "review-1.json").is_file()
    assert (artifacts / "review-2.json").is_file()
    assert (artifacts / "patch.json").is_file()
    events = [
        json.loads(line) for line in (result.run_path / "events.jsonl").read_text().splitlines()
    ]
    assert events[0]["payload"]["recipe"]["version"] == "2.0.0"
    assert any(
        e["event_type"] == "verifier.completed" and e["payload"].get("passed") for e in events
    )


@pytest.mark.asyncio
async def test_v2_skips_revision_after_complete_passing_review(tmp_path):
    model = ScriptedSynthesis(draft_article(), review_payload())
    result = await run_reviewed(tmp_path, model)
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert len(model.requests) == 2


@pytest.mark.asyncio
async def test_v2_stops_partial_after_one_unsuccessful_revision(tmp_path):
    model = ScriptedSynthesis(
        draft_article(), review_payload(failed=True), section_patch(), review_payload(failed=True)
    )
    result = await run_reviewed(tmp_path, model)
    assert result.terminal_state is TerminalState.PARTIAL
    assert result.article_path.is_file()
    assert len(model.requests) == 4


@pytest.mark.asyncio
async def test_v2_empty_review_cannot_succeed(tmp_path):
    empty = {"schema_version": "vidsnap.article-review/v1", "figures": [], "issues": []}
    model = ScriptedSynthesis(draft_article(), empty, section_patch(), empty)
    result = await run_reviewed(tmp_path, model)
    assert result.terminal_state is TerminalState.PARTIAL


@pytest.mark.asyncio
async def test_v2_rejects_patch_to_unflagged_section_and_keeps_draft(tmp_path):
    patch = section_patch()
    patch["sections"][0]["section_index"] = 1
    model = ScriptedSynthesis(draft_article(), review_payload(failed=True), patch)
    result = await run_reviewed(tmp_path, model)
    assert result.terminal_state is TerminalState.FAILED
    assert json.loads((result.run_path / "result.json").read_text()) == draft_article()
    assert len(model.requests) == 3


@pytest.mark.asyncio
async def test_v2_review_provider_failure_retains_auditable_draft(tmp_path):
    model = ScriptedSynthesis(draft_article(), ProviderError("synthetic provider error"))
    result = await run_reviewed(tmp_path, model)
    assert result.terminal_state is TerminalState.FAILED
    assert result.article_path.is_file()
    assert (result.run_path / "artifacts" / "article-v2" / "draft.json").is_file()
    assert json.loads((result.run_path / "result.json").read_text()) == draft_article()


@pytest.mark.asyncio
async def test_v2_editorial_only_revision_does_not_resample(tmp_path):
    model = ScriptedSynthesis(
        draft_article(), review_payload(editorial=True), section_patch(), review_payload()
    )
    result = await run_reviewed(tmp_path, model)
    assert result.terminal_state is TerminalState.SUCCEEDED
    assert len(model.requests[2].evidence) == 8


@pytest.mark.asyncio
async def test_v2_unknown_review_coordinates_fail_closed(tmp_path):
    report = review_payload()
    report["figures"][0]["section_index"] = 999
    result = await run_reviewed(tmp_path, ScriptedSynthesis(draft_article(), report))
    assert result.terminal_state is TerminalState.FAILED


def test_recipe_version_is_explicit_and_rejects_unknown_values():
    with pytest.raises(ValueError):
        ArticleRecipeRunner(recipe_version="v999")


@pytest.mark.asyncio
async def test_v2_failed_visual_gate_is_visible_in_run_index_and_offline_trace(tmp_path):
    from vidsnap.trace.export import export_trace
    from vidsnap.trace.run_index import summarize_run

    model = ScriptedSynthesis(
        draft_article(), review_payload(failed=True), section_patch(), review_payload(failed=True)
    )
    result = await run_reviewed(tmp_path, model)
    summary = summarize_run(result.run_path, command="recipe article")
    assert "visual_captions_supported" in summary["failed_gates"]
    assert summary["terminal_state"] == "PARTIAL"
    assert export_trace(result.run_path, tmp_path / "trace.html").is_file()


@pytest.mark.asyncio
async def test_v2_reserves_initial_frames_and_records_declared_budget(tmp_path):
    from vidsnap.video.sampling import FrameCandidate

    class ManyFrames(FakeMedia):
        async def visual_candidates(self, source, probe):
            return [
                FrameCandidate(timestamp=i + 0.5, score=1, perceptual_hash=f"f-{i}")
                for i in range(100)
            ]

    # Stop after the draft; verify sampling independently of the scripted citations.
    model = ScriptedSynthesis(ProviderError("synthetic failure"))
    result = await run_reviewed(tmp_path, model, ManyFrames(duration_seconds=120, has_audio=False))
    assert len(model.requests[0].evidence) == 32
    manifest = json.loads((result.run_path / "manifest.json").read_text())
    assert manifest["resources"]["max_model_calls"] == 4
    assert manifest["resources"]["max_evidence_frames"] == 96
    assert manifest["resources"]["max_tool_calls"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["duplicate", "wrong_id", "extra_field"])
async def test_v2_malformed_reviews_never_pass(tmp_path, defect):
    report = review_payload()
    if defect == "duplicate":
        report["figures"].append(deepcopy(report["figures"][0]))
    elif defect == "wrong_id":
        report["figures"][0]["evidence_id"] = "frame-999"
    else:
        report["approved"] = True
    result = await run_reviewed(tmp_path, ScriptedSynthesis(draft_article(), report))
    assert result.terminal_state is TerminalState.FAILED


@pytest.mark.asyncio
async def test_v2_supported_verdict_cannot_hide_wrong_timestamp(tmp_path):
    draft = draft_article()
    draft["sections"][0]["figures"][0]["timestamp_seconds"] = 10
    result = await run_reviewed(
        tmp_path,
        ScriptedSynthesis(
            draft,
            review_payload(),
            section_patch(),
            review_payload(failed=True),
        ),
    )
    assert result.terminal_state is TerminalState.PARTIAL
    report = json.loads((result.run_path / "artifacts/article-v2/review-1.json").read_text())
    assert report["figures"][0]["verdict"] == "supported"
    assert (result.run_path / "artifacts/article-v2/patch.json").is_file()


@pytest.mark.asyncio
async def test_v2_rejects_unflagged_title_change(tmp_path):
    patch = section_patch()
    patch["title"] = "Unauthorized title"
    result = await run_reviewed(
        tmp_path,
        ScriptedSynthesis(
            draft_article(),
            review_payload(failed=True),
            patch,
        ),
    )
    assert result.terminal_state is TerminalState.FAILED
    assert (
        json.loads((result.run_path / "result.json").read_text())["title"]
        == draft_article()["title"]
    )


@pytest.mark.asyncio
async def test_v2_global_issue_allows_global_patch_without_touching_sections(tmp_path):
    report = review_payload()
    report["issues"] = [{"section_index": None, "reason": "标题太笼统"}]
    result = await run_reviewed(
        tmp_path,
        ScriptedSynthesis(
            draft_article(),
            report,
            {"title": "具体的新标题"},
            review_payload(),
        ),
    )
    assert result.terminal_state is TerminalState.SUCCEEDED
    output = json.loads((result.run_path / "result.json").read_text())
    assert output["title"] == "具体的新标题"
    assert output["sections"] == draft_article()["sections"]


def test_v2_cli_option_is_exposed_and_invalid_version_fails_before_work(tmp_path):
    from typer.testing import CliRunner

    from tests.ansi import strip_ansi
    from vidsnap.cli import app

    runner = CliRunner()
    help_result = runner.invoke(app, ["recipe", "article", "--help"])
    assert "--recipe-version" in strip_ansi(help_result.stdout)
    video = tmp_path / "synthetic.mp4"
    video.write_bytes(b"synthetic")
    result = runner.invoke(
        app,
        [
            "recipe",
            "article",
            str(video),
            "--output-dir",
            str(tmp_path / "out"),
            "--recipe-version",
            "v999",
        ],
    )
    assert result.exit_code != 0
    assert not (tmp_path / "out").exists()


@pytest.mark.asyncio
async def test_v2_renderer_never_extracts_unrecorded_frames(tmp_path, monkeypatch):
    import vidsnap.recipes.article as recipe_module

    media_arguments = []

    def resolver_spy(evidence, media):
        media_arguments.append(media)
        # Do not let the legacy renderer launch FFmpeg in this offline regression.
        return lambda figure, destination: None

    monkeypatch.setattr(recipe_module, "make_frame_resolver", resolver_spy)
    monkeypatch.setattr(
        recipe_module, "FFmpegMediaPort", lambda: FakeMedia(duration_seconds=120, has_audio=False)
    )
    video = tmp_path / "synthetic.mp4"
    video.write_bytes(b"synthetic, no real media")
    model = ScriptedSynthesis(draft_article(), ProviderError("synthetic review failure"))
    result = await ArticleRecipeRunner(
        system="harness+mock",
        recipe_version="v2",
        synthesis_port=model,
    ).run(video, "图文文章", tmp_path / "out", run_dir=tmp_path / "run")
    assert result.terminal_state is TerminalState.FAILED
    assert media_arguments == [None]
