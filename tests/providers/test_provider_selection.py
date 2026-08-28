"""RED tests for provider selection and injection contracts."""

from dataclasses import fields
from pathlib import Path

import pytest

from vidsnap.benchmark.profiles import BenchmarkProfile
from vidsnap.config import QWEN_MODEL, HarnessConfig
from vidsnap.contracts import AgentDecision, ToolPlan
from vidsnap.harness import VideoHarness
from vidsnap.providers import MockProvider
from vidsnap.providers.base import AgentStepRequest
from vidsnap.recipes import InterviewRecipeRunner


def test_video_harness_provider_injection_and_conflicts() -> None:
    mock = MockProvider()
    config = HarnessConfig(api_key="fake")
    harness = VideoHarness(config=config, provider=mock)
    assert harness.model is mock
    assert harness.planner is mock
    assert harness.agent_model is mock
    assert harness.recognizer is None

    with pytest.raises(ValueError):
        VideoHarness(config=config, provider=mock, model=object())
    with pytest.raises(ValueError):
        VideoHarness(config=config, provider=mock, planner=object())


def test_interview_runner_provider_injection_and_conflict() -> None:
    mock = MockProvider()
    runner = InterviewRecipeRunner(provider=mock)
    assert runner._agent_model is mock
    assert runner._recognizer is None

    with pytest.raises(ValueError):
        InterviewRecipeRunner(provider=mock, agent_model=object())


def test_step_request_and_decisions_hide_provider_fields() -> None:
    forbidden = {"provider", "model", "base_url"}

    assert not forbidden & {f.name for f in fields(AgentStepRequest)}
    assert not forbidden & set(ToolPlan.model_fields)
    assert not forbidden & set(AgentDecision.model_fields)


def test_benchmark_profile_model_defaults_and_lock() -> None:
    profile = BenchmarkProfile(name="x", local_root=Path("."), license="x")
    assert profile.model == QWEN_MODEL

    with pytest.raises(ValueError):
        BenchmarkProfile(name="x", local_root=Path("."), license="x", model="other")
