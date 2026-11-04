"""The article recipe: one local video to an illustrated, evidence-cited article.

V1 uses the evaluation's t1 machinery unchanged. Opt-in v2 adds actual-image
review and one bounded local revision through the same pinned model port.
Both versions leave ordinary RunBundles and render articles to the output directory.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from vidsnap.contracts import HarnessPolicy, TerminalState, VideoSource, default_loop_spec
from vidsnap.eval.attribution import read_evidence
from vidsnap.eval.providers import EndpointName, SynthesisPort
from vidsnap.eval.render import make_frame_resolver, render_output
from vidsnap.eval.suite import EvalItem, ItemInputs, SourceVideo
from vidsnap.eval.systems import BuildOptions, build_components, parse_system
from vidsnap.eval.tasks import PROMPT_VERSION, get_task
from vidsnap.loop.run_bundle import RunBundle
from vidsnap.recipes.article_review import (
    REVIEWED_VERSION,
    ReviewedArticlePolicy,
    reviewed_registry,
)
from vidsnap.runtime import HarnessKernel, RecipeIdentity, RunContext, default_plugin_registry
from vidsnap.video.ports import FFmpegPort
from vidsnap.video.probe import FFmpegMediaPort
from vidsnap.video.sampling import AdaptiveSampler

RECIPE_ID = "recipe/article"
DEFAULT_GOAL = "把这段视频改写成一篇图文并茂的中文公众号文章，配图要对应具体内容。"


@dataclass(frozen=True, slots=True)
class ArticleRecipeResult:
    """Where one article run ended up."""

    terminal_state: TerminalState
    run_path: Path
    output_dir: Path
    article_path: Path | None
    figures: int


class ArticleRecipeRunner:
    """Runs the article recipe for one local video.

    ``system`` is an evaluation system name (``harness+<model>``); ``harness+mock``
    runs fully offline with an injected media port, which is how tests use it.
    """

    def __init__(
        self,
        *,
        system: str = "harness+qwen3.8-max",
        endpoint: EndpointName = "dashscope",
        media: FFmpegPort | None = None,
        timeout_seconds: float = 900.0,
        transport: httpx.AsyncBaseTransport | None = None,
        recipe_version: Literal["v1", "v2"] = "v1",
        synthesis_port: SynthesisPort | None = None,
    ) -> None:
        if recipe_version not in ("v1", "v2"):
            raise ValueError("recipe_version must be v1 or v2")
        if synthesis_port is not None and recipe_version != "v2":
            raise ValueError("synthesis_port injection is available only for article v2")
        self._recipe_version = recipe_version
        self._synthesis_port = synthesis_port
        self._spec = parse_system(system)
        if self._spec.kind != "harness":
            raise ValueError("the article recipe runs harness systems only")
        self._options = BuildOptions(
            endpoint=endpoint, timeout_seconds=timeout_seconds, transport=transport
        )
        self._media = media

    async def run(
        self,
        video: Path,
        goal: str,
        output_dir: Path,
        *,
        run_dir: Path | None = None,
    ) -> ArticleRecipeResult:
        """Run the bounded loop on ``video`` and render the article into ``output_dir``."""
        task = get_task("t1")
        item = EvalItem(
            item_id="recipe-article",
            status="needs_reference",
            source=SourceVideo(kind="owner", licence="owner, local recipe run", language="zh"),
            inputs=ItemInputs(goal=goal),
        )
        media = self._media or FFmpegMediaPort()
        components = build_components(self._spec, task, item, media=media, options=self._options)
        run_path = (run_dir or Path.cwd() / "run" / str(uuid.uuid4())).expanduser().resolve()
        if self._synthesis_port is not None:
            components.task_model = self._synthesis_port
            components.provider_identity = self._synthesis_port.identity
        reviewed = self._recipe_version == "v2"
        policy = (
            HarnessPolicy(max_model_calls=4, max_tool_calls=3, max_iterations=2)
            if reviewed
            else HarnessPolicy()
        )
        loop_spec = default_loop_spec()
        if reviewed:
            loop_spec = loop_spec.model_copy(
                update={
                    "max_repair_rounds": 1,
                    "budgets": loop_spec.budgets.model_copy(
                        update={
                            "max_model_calls": 4,
                            "max_tool_calls": 3,
                            "max_iterations": 2,
                        }
                    ),
                }
            )
        identity = components.provider_identity
        bundle = RunBundle.create(
            run_path,
            loop_spec=loop_spec,
            provider_url=identity.base_url,
            provider_identity=identity,
        )
        context: RunContext[Any, Any] = RunContext(
            source=VideoSource(path=video),
            policy=policy,
            bundle=bundle,
            task_adapter=components.adapter,
            task_model=components.task_model,
            media=components.media,
            sampler=AdaptiveSampler(),
            recognizer=components.recognizer,
            result_writer=bundle.write_result,
            provider_identity=identity,
            speech_recognizer_identity=components.recognizer_identity,
            recipe=RecipeIdentity(
                id=RECIPE_ID, version=REVIEWED_VERSION if reviewed else PROMPT_VERSION
            ),
        )
        kernel: HarnessKernel[Any, Any] = HarnessKernel(
            policy=ReviewedArticlePolicy(components.adapter) if reviewed else components.policy,
            registry=reviewed_registry() if reviewed else default_plugin_registry(),
        )
        result = await kernel.run(context)
        article_path: Path | None = None
        figures = 0
        if result.output is not None:
            resolver = make_frame_resolver(
                read_evidence(run_path),
                video if not reviewed and self._media is None else None,
            )
            render = render_output(result.output, output_dir, resolver)
            images = render.get("images")
            figures = images if isinstance(images, int) else 0
            candidate = output_dir / "article.md"
            article_path = candidate if candidate.is_file() else None
        return ArticleRecipeResult(
            terminal_state=result.terminal_state,
            run_path=run_path,
            output_dir=output_dir,
            article_path=article_path,
            figures=figures,
        )
