"""Command-line entry point for VidSnap Harness."""

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from vidsnap.config import HarnessConfig
from vidsnap.contracts import HarnessPolicy, TerminalState, VideoGoal, VideoSource
from vidsnap.harness import VideoHarness
from vidsnap.publishing.repository import find_repository_root
from vidsnap.publishing.service import publish_video
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
def manifest(run_dir: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Print the redacted manifest from a completed local RunBundle."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise typer.BadParameter("run directory does not contain manifest.json")
    typer.echo(manifest_path.read_text(encoding="utf-8"))


@app.command()
def publish(
    video: Annotated[Path, typer.Option(exists=True, file_okay=True, dir_okay=False)],
    transcript: Annotated[Path, typer.Option(exists=True, file_okay=True, dir_okay=False)],
    run_dir: Annotated[Path, typer.Option("--run-dir")],
    output_dir: Annotated[Path, typer.Option("--output-dir")],
) -> None:
    """Opt-in: run the bounded publishing pipeline and export deliverables locally."""
    try:
        result = asyncio.run(
            publish_video(
                video=video,
                transcript_path=transcript,
                run_dir=run_dir,
                output_dir=output_dir,
                repository_root=find_repository_root(Path.cwd()),
            )
        )
    except (ValueError, FileExistsError) as error:
        typer.echo(f"publish failed: {error}", err=True)
        raise typer.Exit(code=1) from None
    except Exception:
        typer.echo("publish failed", err=True)
        raise typer.Exit(code=1) from None
    payload: dict[str, object] = {
        "terminal_state": result.terminal_state.value,
        "run_path": str(result.run_path),
        "run_id": result.run_id,
        "deliverables": [
            deliverable.model_dump(mode="json") for deliverable in result.publishing.deliverables
        ]
        if result.publishing is not None
        else [],
        "verification": (
            {"passed": result.verification.passed, "gates": result.verification.gates}
            if result.verification is not None
            else None
        ),
        "failure_reason": result.failure_reason,
    }
    typer.echo(json.dumps(payload, ensure_ascii=True))
    if result.terminal_state is not TerminalState.SUCCEEDED:
        raise typer.Exit(code=1)


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
