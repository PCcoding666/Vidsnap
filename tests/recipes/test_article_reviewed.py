"""Offline regression tests for the opt-in reviewed article workflow."""

import asyncio
import json

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
from vidsnap.eval.providers import MockSynthesis
from vidsnap.eval.suite import EvalItem, ItemInputs, SourceVideo
from vidsnap.eval.tasks import get_task
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.plugins.builtin.sample_evidence import DenseSampleEvidencePlugin, SampleEvidenceArgs
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
