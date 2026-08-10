"""Command-line entry point for VidSnap Harness."""

import asyncio
import json
from pathlib import Path

import typer

from vidsnap.contracts import HarnessPolicy, VideoGoal, VideoSource
from vidsnap.harness import VideoHarness

app = typer.Typer(
    name="vidsnap",
    help="VidSnap Harness: evidence-grounded video analysis.",
    no_args_is_help=True,
)
benchmark_app = typer.Typer(help="Run fair Direct-vs-Harness benchmarks.")
app.add_typer(benchmark_app, name="benchmark")


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


@benchmark_app.command("run")
def benchmark_run() -> None:
    """Run a configured local benchmark profile."""
    typer.echo("Benchmark runners are installed with the harness benchmark module.")


@benchmark_app.command("compare")
def benchmark_compare() -> None:
    """Compare Direct and Harness results from a local benchmark run."""
    typer.echo("Benchmark comparison is installed with the harness benchmark module.")


def main() -> None:
    """Run the VidSnap Harness command line application."""
    app()
