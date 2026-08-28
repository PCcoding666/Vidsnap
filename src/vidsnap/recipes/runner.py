"""Interview recipe run orchestration over the bounded kernel loop."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from vidsnap.config import TOKEN_PLAN_BASE_URL, HarnessConfig
from vidsnap.contracts import (
    HarnessPolicy,
    TerminalState,
    VideoGoal,
    VideoSource,
    default_loop_spec,
)
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.plugins.base import SpeechRecognizerAdapter, TranscriptionPort
from vidsnap.providers.asr import QwenAsrRecognizer
from vidsnap.providers.base import AgentModelPort
from vidsnap.providers.qwen import QwenCompatibleClient
from vidsnap.recipes.interview import InterviewRecipeResult
from vidsnap.recipes.render import InterviewRecipeArtifacts, render_interview_recipe
from vidsnap.recipes.task import InterviewRecipeTaskAdapter
from vidsnap.runtime import AgenticPolicy, HarnessKernel, RunContext, default_plugin_registry
from vidsnap.tasks.base import TaskAdapter, TaskVerification
from vidsnap.trace.export import export_trace
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import FFmpegMediaPort
from vidsnap.video.sampling import AdaptiveSampler

__all__ = ["InterviewRecipeRunner", "InterviewRecipeRunResult"]

_INTERVIEW_OBJECTIVE = (
    "Produce a grounded interview record from the captured local transcript and "
    "frame evidence of this video. Retain every captured dialogue turn verbatim "
    "with its speaker and timing, and ground all commentary and brief points in "
    "captured evidence identifiers. Never invent, drop, or embellish dialogue."
)


@dataclass(frozen=True, slots=True)
class InterviewRecipeRunResult:
    """Terminal outcome of an interview recipe run."""

    terminal_state: TerminalState
    artifacts: InterviewRecipeArtifacts | None = None
    failure_reason: str | None = None
    verification: TaskVerification | None = None


class InterviewRecipeRunner:
    """Runs an interview recipe against a video source.

    Construction is dependency-injected; every dependency is optional so the
    runner can be assembled partially in offline or test environments. The
    goal, loop budgets, tool registry, and provider endpoint are fixed recipe
    constants that neither the model nor the caller may choose.
    """

    def __init__(
        self,
        *,
        config: HarnessConfig | None = None,
        media: FFmpegPort | None = None,
        recognizer: TranscriptionPort | None = None,
        sampler: AdaptiveSampler | None = None,
        agent_model: AgentModelPort | None = None,
    ) -> None:
        self._config = config
        self._media = media
        self._recognizer = recognizer
        self._sampler = sampler
        self._agent_model = agent_model

    async def run(self, source: VideoSource, output_dir: Path) -> InterviewRecipeRunResult:
        """Execute the recipe for ``source`` into ``output_dir``."""
        config = self._config or HarnessConfig.from_env()
        try:
            media = self._media or FFmpegMediaPort()
            sampler = self._sampler or AdaptiveSampler()
            agent_model: AgentModelPort = self._agent_model or QwenCompatibleClient(
                api_key=config.api_key,
                model_concurrency=config.model_concurrency,
                timeout_seconds=config.request_timeout_seconds,
            )
            recognizer: TranscriptionPort | None = self._recognizer or SpeechRecognizerAdapter(
                QwenAsrRecognizer(api_key=config.api_key)
            )
            return await self._run_bounded(
                source,
                output_dir,
                media=media,
                sampler=sampler,
                agent_model=agent_model,
                recognizer=recognizer,
            )
        except Exception:
            return InterviewRecipeRunResult(
                terminal_state=TerminalState.FAILED,
                failure_reason="unexpected recipe runner error",
            )

    async def _run_bounded(
        self,
        source: VideoSource,
        output_dir: Path,
        *,
        media: FFmpegPort,
        sampler: AdaptiveSampler,
        agent_model: AgentModelPort,
        recognizer: TranscriptionPort | None,
    ) -> InterviewRecipeRunResult:
        """Drive one kernel-owned agentic run inside a private temporary workspace."""
        with tempfile.TemporaryDirectory(prefix="vidsnap-recipe-") as workspace:
            workspace_path = Path(workspace)
            bundle = RunBundle.create(
                workspace_path / "run",
                loop_spec=default_loop_spec(),
                provider_url=TOKEN_PLAN_BASE_URL,
            )
            context: RunContext[InterviewRecipeResult, AgentModelPort] = RunContext(
                source=source,
                policy=HarnessPolicy(tool_mode="agentic"),
                bundle=bundle,
                task_adapter=cast(
                    TaskAdapter[InterviewRecipeResult, AgentModelPort],
                    InterviewRecipeTaskAdapter(_interview_goal()),
                ),
                task_model=agent_model,
                media=media,
                sampler=sampler,
                recognizer=recognizer,
                result_writer=bundle.write_result,
                agent_model=agent_model,
            )
            kernel: HarnessKernel[InterviewRecipeResult, AgentModelPort] = HarnessKernel(
                policy=AgenticPolicy(),
                registry=default_plugin_registry(),
            )
            kernel_result = await kernel.run(context)
            if not (
                kernel_result.terminal_state is TerminalState.SUCCEEDED
                and isinstance(kernel_result.output, InterviewRecipeResult)
                and kernel_result.verification is not None
                and kernel_result.verification.passed
            ):
                return InterviewRecipeRunResult(
                    terminal_state=kernel_result.terminal_state,
                    failure_reason=kernel_result.failure_reason,
                    verification=kernel_result.verification,
                )
            trace_path = export_trace(bundle.path, workspace_path / "trace.html")
            artifacts = render_interview_recipe(
                kernel_result.output,
                output_dir,
                _ascii_safe_html(trace_path.read_text(encoding="utf-8")).encode("ascii"),
            )
            return InterviewRecipeRunResult(
                terminal_state=TerminalState.SUCCEEDED,
                artifacts=artifacts,
                verification=kernel_result.verification,
            )


def _interview_goal() -> VideoGoal:
    """Return the fixed, private, source-preserving interview objective."""
    return VideoGoal(objective=_INTERVIEW_OBJECTIVE)


def _ascii_safe_html(html_text: str) -> str:
    """Escape every non-ASCII code point as a numeric character reference.

    The shared trace template carries typographic Unicode; numeric references
    keep the page meaning and every ASCII claim/tool identifier byte-identical
    while making the exported HTML fully ASCII-safe.
    """
    return "".join(
        character if ord(character) < 128 else f"&#{ord(character)};" for character in html_text
    )
