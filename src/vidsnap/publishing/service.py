"""Opt-in local publishing service: one bounded run plus atomic external export."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from vidsnap.config import TOKEN_PLAN_BASE_URL, HarnessConfig
from vidsnap.contracts import (
    HarnessPolicy,
    LoopBudgets,
    LoopSpec,
    TerminalState,
    VideoGoal,
    VideoSource,
)
from vidsnap.contracts.loopspec import SkillName
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.providers.qwen import QwenCompatibleClient
from vidsnap.publishing.contracts import PublishingResult
from vidsnap.publishing.orchestrator import publish_draft
from vidsnap.publishing.policy import _SAMPLE_MAX_FRAMES, PublishingPolicy
from vidsnap.publishing.task import PublishingDraft, PublishingModelPort, PublishingTaskAdapter
from vidsnap.runtime import HarnessKernel, RunContext, default_plugin_registry
from vidsnap.tasks.base import TaskVerification
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import FFmpegMediaPort
from vidsnap.video.sampling import AdaptiveSampler

if TYPE_CHECKING:
    from vidsnap.runtime.policies import ExecutionPolicy

_PUBLISHING_GOAL = VideoGoal(objective="Produce the publishing package")

# Long-article drafting needs a bounded timeout above the global 120-second
# default but strictly inside the 900-second loop wall cap; it is fixed here
# so neither the model nor the CLI can choose it.
PUBLISHING_REQUEST_TIMEOUT_SECONDS = 600.0

_CAP_TOOL_CALLS = 1
_CAP_MODEL_CALLS = 1
_CAP_EVIDENCE_FRAMES = _SAMPLE_MAX_FRAMES

_PUBLISHING_SKILLS: tuple[SkillName, ...] = (
    "probe_media",
    "sample_evidence",
    "synthesize_result",
    "verify_claims",
)


def publishing_loop_spec() -> LoopSpec:
    """LoopSpec matching the fixed publishing flow: 1 tool, 1 model, 12 frames."""
    return LoopSpec(
        allowed_skills=_PUBLISHING_SKILLS,
        budgets=LoopBudgets(
            max_tool_calls=_CAP_TOOL_CALLS,
            max_model_calls=_CAP_MODEL_CALLS,
            max_evidence_frames=_CAP_EVIDENCE_FRAMES,
        ),
    )


def build_publishing_model(config: HarnessConfig) -> QwenCompatibleClient:
    """Build the default publishing client with the fixed long-request timeout."""
    return QwenCompatibleClient(
        api_key=config.api_key,
        model_concurrency=config.model_concurrency,
        timeout_seconds=PUBLISHING_REQUEST_TIMEOUT_SECONDS,
    )


@dataclass(frozen=True, slots=True)
class PublishServiceResult:
    """Content-safe outcome of one publishing run: references only, never texts."""

    terminal_state: TerminalState
    run_path: Path
    run_id: str
    publishing: PublishingResult | None
    verification: TaskVerification | None
    failure_reason: str | None


async def publish_video(
    *,
    video: Path,
    transcript_path: Path,
    run_dir: Path,
    output_dir: Path,
    repository_root: Path,
    config: HarnessConfig | None = None,
    media: FFmpegPort | None = None,
    model: PublishingModelPort | None = None,
    policy: ExecutionPolicy[PublishingDraft, PublishingModelPort] | None = None,
) -> PublishServiceResult:
    """Run the fixed publishing policy once and export deliverables externally."""
    repository = repository_root.resolve()
    resolved_run_dir = _require_external_dir(run_dir, repository, "run_dir")
    resolved_output_dir = _require_external_dir(output_dir, repository, "output_dir")
    if resolved_run_dir == resolved_output_dir or resolved_run_dir.is_relative_to(
        resolved_output_dir
    ):
        raise ValueError("run_dir and output_dir must be distinct, non-overlapping directories")
    if resolved_output_dir.is_relative_to(resolved_run_dir):
        raise ValueError("run_dir and output_dir must be distinct, non-overlapping directories")
    resolved_video = _require_external_file(video, repository, "video")
    resolved_transcript = _require_external_file(transcript_path, repository, "transcript")
    transcript_text = resolved_transcript.read_text(encoding="utf-8")
    if not transcript_text.strip():
        raise ValueError("transcript must be non-blank")

    effective_config = config or HarnessConfig.from_env()
    media_port = media or FFmpegMediaPort()
    model_port: PublishingModelPort = model or build_publishing_model(effective_config)

    bundle = RunBundle.create(
        resolved_run_dir,
        loop_spec=publishing_loop_spec(),
        provider_url=TOKEN_PLAN_BASE_URL,
    )
    adapter = PublishingTaskAdapter(goal=_PUBLISHING_GOAL, transcript=transcript_text)
    context: RunContext[PublishingDraft, PublishingModelPort] = RunContext(
        source=VideoSource(path=resolved_video),
        policy=HarnessPolicy(max_tool_calls=1, max_model_calls=1, max_evidence_frames=12),
        bundle=bundle,
        task_adapter=adapter,
        task_model=model_port,
        media=media_port,
        sampler=AdaptiveSampler(video_kind="talking"),
        agent_model=None,
        recognizer=None,
    )

    exported: dict[str, PublishingResult] = {}

    def write_publishing(draft: PublishingDraft) -> None:
        if context.terminal_state is not TerminalState.SUCCEEDED:
            return
        verification = context.verification
        if verification is None or not verification.passed:
            return
        cap_violation = audit_publishing_caps(
            tool_calls=context.tool_calls,
            model_calls=context.model_calls,
            evidence_frames=_frame_count(context),
        )
        if cap_violation is not None:
            raise ValueError(f"publishing caps violated: {cap_violation}")
        exported["publishing"] = publish_draft(
            repository_root=repository,
            output_dir=resolved_output_dir,
            run_id=bundle.run_id,
            generated_at=datetime.now(timezone.utc),
            transcript=transcript_text,
            draft=draft,
            evidence=tuple(context.evidence),
        )

    writer: Callable[[PublishingDraft], object] = write_publishing
    context.result_writer = writer

    kernel: HarnessKernel[PublishingDraft, PublishingModelPort] = HarnessKernel(
        policy=policy or PublishingPolicy(),
        registry=default_plugin_registry(),
    )
    kernel_result = await kernel.run(context)
    return PublishServiceResult(
        terminal_state=kernel_result.terminal_state,
        run_path=bundle.path,
        run_id=bundle.run_id,
        publishing=exported.get("publishing"),
        verification=kernel_result.verification,
        failure_reason=kernel_result.failure_reason,
    )


def audit_publishing_caps(*, tool_calls: int, model_calls: int, evidence_frames: int) -> str | None:
    """Return one content-safe violation detail unless the fixed caps held exactly."""
    problems: list[str] = []
    if tool_calls != _CAP_TOOL_CALLS:
        problems.append(f"sample_evidence tool calls {tool_calls} != {_CAP_TOOL_CALLS}")
    if model_calls != _CAP_MODEL_CALLS:
        problems.append(f"qwen3.8-max model calls {model_calls} != {_CAP_MODEL_CALLS}")
    if evidence_frames > _CAP_EVIDENCE_FRAMES:
        problems.append(f"evidence frames {evidence_frames} > {_CAP_EVIDENCE_FRAMES}")
    return "; ".join(problems) if problems else None


def _frame_count(context: RunContext[PublishingDraft, PublishingModelPort]) -> int:
    return sum(1 for item in context.evidence if item.modality == "frame")


def _require_external_dir(path: Path, repository: Path, label: str) -> Path:
    """Require one absolute directory strictly outside the repository root."""
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    resolved = path.resolve()
    if resolved == repository or resolved.is_relative_to(repository):
        raise ValueError(f"{label} must be located strictly outside the repository root")
    return resolved


def _require_external_file(path: Path, repository: Path, label: str) -> Path:
    """Require one resolved, absolute regular file strictly outside the repository."""
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    resolved = path.resolve()
    if resolved == repository or resolved.is_relative_to(repository):
        raise ValueError(f"{label} must be located strictly outside the repository root")
    if not resolved.is_file():
        raise ValueError(f"{label} must be an existing regular file")
    return resolved
