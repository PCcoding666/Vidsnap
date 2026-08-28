"""Command-line entry point for VidSnap Harness."""

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from vidsnap.config import HarnessConfig
from vidsnap.contracts import HarnessPolicy, TerminalState, VideoGoal, VideoSource
from vidsnap.demo import replay_demo_run
from vidsnap.harness import VideoHarness
from vidsnap.recipes.runner import InterviewRecipeRunner
from vidsnap.trace.export import export_trace

app = typer.Typer(
    name="vidsnap",
    help="VidSnap Harness: evidence-grounded video analysis.",
    no_args_is_help=True,
)
benchmark_app = typer.Typer(help="Run fair Direct-vs-Harness benchmarks.")
app.add_typer(benchmark_app, name="benchmark")
trace_app = typer.Typer(help="Export truthful local run traces.")
app.add_typer(trace_app, name="trace")
recipe_app = typer.Typer(help="Run grounded editorial recipes.")
app.add_typer(recipe_app, name="recipe")


@app.callback()
def root() -> None:
    """VidSnap Harness command group."""


@app.command()
def analyze(
    video: Path = typer.Argument(..., exists=True, readable=True),
    goal: str = typer.Option("Summarize the video.", "--goal", min=1),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
) -> None:
    """Analyze one local video through the bounded evidence harness."""
    result = asyncio.run(
        VideoHarness().run(
            VideoSource(path=video),
            VideoGoal(objective=goal),
            HarnessPolicy(output_dir=output_dir),
        )
    )
    typer.echo(
        json.dumps(
            {
                "terminal_state": result.terminal_state.value,
                "run_path": str(result.run_path),
                "claims": [claim.model_dump(mode="json") for claim in result.claims],
            },
            ensure_ascii=True,
        )
    )


@app.command()
def demo(output_dir: Path = typer.Option(Path("vidsnap-demo"), "--output-dir")) -> None:
    """Replay the packaged synthetic demo run into a fresh output directory."""
    resolved = output_dir.expanduser().resolve()
    try:
        report = replay_demo_run(resolved)
    except (FileExistsError, ValueError) as error:
        typer.echo(f"Demo refused: {error}")
        raise typer.Exit(code=2) from None
    typer.echo("Loaded VidSnap packaged synthetic replay (not live model generation)")
    typer.echo("Goal: Summarize a synthetic 20-second demo clip with grounded observations")
    typer.echo(f"Replayed {report.counts.steps} agent steps")
    typer.echo(f"Tool Calls: {report.budget.tool_calls}")
    typer.echo(f"Loaded {report.counts.evidence} evidence items")
    typer.echo(f"Verified {report.counts.claims_grounded}/{report.counts.claims_total} claims")
    typer.echo("Verification: passed")
    typer.echo("Budget respected")
    typer.echo(f"Final Artifact: {resolved / 'run' / 'result.json'}")
    typer.echo("Trace exported")
    typer.echo(f"Trace: {resolved / 'trace.html'}")


@recipe_app.command("interview")
def recipe_interview(
    video: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(..., "--output-dir"),
) -> None:
    """Produce the grounded interview record for one local video."""
    resolved_video = video.expanduser().resolve()
    resolved_output = output_dir.expanduser().resolve()
    result = asyncio.run(
        InterviewRecipeRunner().run(VideoSource(path=resolved_video), resolved_output)
    )
    payload: dict[str, object] = {"terminal_state": result.terminal_state.value}
    artifacts = result.artifacts
    succeeded = False
    if result.terminal_state is TerminalState.SUCCEEDED and artifacts is not None:
        succeeded = True
        payload["artifacts"] = [
            str(artifacts.transcript_path),
            str(artifacts.article_path),
            str(artifacts.brief_path),
            str(artifacts.trace_path),
        ]
    typer.echo(json.dumps(payload, ensure_ascii=True))
    if not succeeded:
        raise typer.Exit(code=1)


@app.command()
def manifest(run_dir: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Print the redacted manifest from a completed local RunBundle."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise typer.BadParameter("run directory does not contain manifest.json")
    typer.echo(manifest_path.read_text(encoding="utf-8"))


@trace_app.command("export")
def trace_export(
    source: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o", help="Destination HTML file.")],
    include_thumbnails: Annotated[
        bool,
        typer.Option(
            "--include-thumbnails",
            help="Embed bounded bundle-local images; never enabled by default.",
        ),
    ] = False,
) -> None:
    """Render one RunBundle, legacy result dir, or benchmark case to offline HTML."""
    exported = export_trace(source.resolve(), output.resolve(), include_thumbnails)
    typer.echo(str(exported))


@app.command()
def serve() -> None:
    """Serve the stateless local FastAPI adapter on 127.0.0.1 by default."""
    try:
        import uvicorn
    except ImportError as error:
        raise typer.BadParameter("install the 'server' extra to use vidsnap serve") from error
    from vidsnap.api import DEFAULT_HOST, create_app

    uvicorn.run(create_app(), host=DEFAULT_HOST, port=8000)


@app.command()
def conformance() -> None:
    """Run offline package conformance checks when the release module is available."""
    try:
        from vidsnap.conformance import run_conformance
    except ImportError:
        typer.echo("Conformance checks are not installed yet.", err=True)
        raise typer.Exit(code=1) from None
    report = run_conformance()
    typer.echo(json.dumps(report.model_dump(mode="json"), ensure_ascii=True))
    if not report.passed:
        raise typer.Exit(code=1)


def _benchmark_availability(operation: str) -> dict[str, str | bool]:
    """Expose an honest offline-safe benchmark availability result."""
    config = HarnessConfig.from_env()
    if not config.api_key:
        return {
            "status": "BLOCKED_LIVE_BENCHMARK",
            "operation": operation,
            "reason": "No local provider credential is configured; no live benchmark was run.",
            "provider_configured": False,
        }
    return {
        "status": "NOT_YET_SUPERIOR",
        "operation": operation,
        "reason": (
            "A local dataset manifest and evaluator are required before a live comparison can run."
        ),
        "provider_configured": True,
    }


@benchmark_app.command("run")
def benchmark_run() -> None:
    """Report whether a safe live benchmark invocation is currently possible."""
    typer.echo(json.dumps(_benchmark_availability("run"), ensure_ascii=True))


@benchmark_app.command("compare")
def benchmark_compare() -> None:
    """Report whether a measured local Direct-vs-Harness comparison is available."""
    typer.echo(json.dumps(_benchmark_availability("compare"), ensure_ascii=True))


def main() -> None:
    """Run the VidSnap Harness command line application."""
    app()
