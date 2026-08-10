"""Local-only, stateless HTTP adapter with per-request temporary RunBundles."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from vidsnap.contracts import HarnessPolicy, VideoGoal, VideoSource, default_loop_spec
from vidsnap.harness import HarnessRunResult, VideoHarness

DEFAULT_HOST = "127.0.0.1"


class AnalyzeRequest(BaseModel):
    """HTTP input deliberately excludes keys, model names, prompts, and provider URLs."""

    model_config = ConfigDict(extra="forbid")

    source: VideoSource
    goal: VideoGoal
    policy: HarnessPolicy = Field(default_factory=HarnessPolicy)


def _result_payload(result: HarnessRunResult) -> dict[str, object]:
    return {
        "terminal_state": result.terminal_state.value,
        "result": result.result.model_dump(mode="json") if result.result is not None else None,
        "failure_reason": result.failure_reason,
        "verification": (
            result.verification.model_dump(mode="json") if result.verification is not None else None
        ),
    }


async def _run_request(
    request: AnalyzeRequest,
    harness_factory: Callable[[], VideoHarness],
) -> HarnessRunResult:
    temporary_root = Path(tempfile.mkdtemp(prefix="vidsnap-http-"))
    task: asyncio.Task[HarnessRunResult] | None = None
    try:
        policy = request.policy.model_copy(update={"output_dir": temporary_root / "run"})
        task = asyncio.create_task(
            harness_factory().run(request.source, request.goal, policy),
        )
        return await task
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        shutil.rmtree(temporary_root, ignore_errors=True)


def create_app(
    harness_factory: Callable[[], VideoHarness] = VideoHarness,
) -> FastAPI:
    """Create the no-users, no-jobs, local FastAPI surface."""
    app = FastAPI(title="VidSnap Harness", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "stateful_jobs": False,
            "default_host": DEFAULT_HOST,
        }

    @app.get("/v1/manifest")
    async def manifest() -> dict[str, object]:
        return {
            "loop_spec": default_loop_spec().model_dump(mode="json"),
            "stateful_jobs": False,
        }

    @app.post("/v1/analyze")
    async def analyze(request: AnalyzeRequest) -> JSONResponse:
        result = await _run_request(request, harness_factory)
        return JSONResponse(_result_payload(result))

    @app.post("/v1/analyze/stream")
    async def analyze_stream(request: AnalyzeRequest) -> StreamingResponse:
        async def events():
            result = await _run_request(request, harness_factory)
            yield f"event: result\ndata: {json.dumps(_result_payload(result))}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app
