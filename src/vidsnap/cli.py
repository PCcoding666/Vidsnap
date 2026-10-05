"""Command-line entry point for VidSnap Harness."""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from vidsnap.benchmark.trust import TrustEvaluationInput, evaluate_trust
from vidsnap.config import HarnessConfig
from vidsnap.contracts import HarnessPolicy, TerminalState, VideoGoal, VideoSource
from vidsnap.demo import replay_demo_run
from vidsnap.harness import VideoHarness
from vidsnap.plugins import PluginRegistry, ToolPlugin, discovery
from vidsnap.plugins.project import validate_plugin_project
from vidsnap.recipes.runner import InterviewRecipeRunner
from vidsnap.trace.export import export_trace
from vidsnap.trace.pricing import LoadedPriceTable, load_price_table
from vidsnap.trace.run_index import (
    INDEX_FILE_NAME,
    RunReview,
    append_index_record,
    read_index,
    render_run_table,
    resolve_run_id,
    review_record,
    summarize_run,
)

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
plugin_app = typer.Typer(help="Validate and test local plugin projects.")
app.add_typer(plugin_app, name="plugin")
runs_app = typer.Typer(help="List and review runs in the local run index.")
app.add_typer(runs_app, name="runs")


_RUNS_ROOT_HELP = (
    "Directory that keeps each RunBundle and the run index (index.jsonl); defaults to ./run."
)
_PRICE_TABLE_HELP = (
    "Your vidsnap.price-table/v1 JSON file; without it the run index records cost as null."
)


RunsRootOption = Annotated[
    Path, typer.Option("--runs-root", envvar="VIDSNAP_RUNS_ROOT", help=_RUNS_ROOT_HELP)
]
PriceTableOption = Annotated[
    Path | None,
    typer.Option("--price-table", envvar="VIDSNAP_PRICE_TABLE", help=_PRICE_TABLE_HELP),
]


def _load_prices(path: Path | None) -> LoadedPriceTable | None:
    """Validate a supplied price table before any run starts; exit 2 when invalid."""
    if path is None:
        return None
    try:
        return load_price_table(path.expanduser())
    except ValueError as error:
        typer.echo(f"Price table refused: {error}", err=True)
        raise typer.Exit(code=2) from None


def _index_run(
    run_path: Path | None,
    runs_root: Path,
    *,
    command: str,
    prices: LoadedPriceTable | None,
) -> None:
    """Append the finished run to the run index; never change the run's outcome."""
    if run_path is None or not (run_path / "manifest.json").is_file():
        return
    try:
        append_index_record(runs_root, summarize_run(run_path, command=command, price_table=prices))
    except (OSError, ValueError) as error:
        typer.echo(f"Run index not updated: {type(error).__name__}", err=True)


def _plugin_error() -> None:
    """Print one generic, redacted plugin CLI result and exit with code 2."""
    typer.echo(json.dumps({"status": "ERROR"}, ensure_ascii=True, separators=(",", ":")))
    raise typer.Exit(code=2) from None


def _normalize_json_schema(node: object) -> object:
    """Return a semantic copy of a JSON schema for equality comparison.

    Recursively drops ``title`` and ``description`` keys from mappings,
    recursively normalizes list items, and sorts only ``required`` name
    lists; a missing ``required`` list on an object schema is treated as
    empty. Every other value is preserved as-is.
    """
    if isinstance(node, dict):
        normalized: dict[str, object] = {}
        for key, value in node.items():
            if key in ("title", "description"):
                continue
            if key == "required" and isinstance(value, list):
                normalized[key] = sorted(value)
                continue
            normalized[key] = _normalize_json_schema(value)
        if normalized.get("type") == "object" and "required" not in normalized:
            normalized["required"] = []
        return normalized
    if isinstance(node, list):
        return [_normalize_json_schema(item) for item in node]
    return node


@plugin_app.command("validate")
def plugin_validate(project: Path = typer.Argument(...)) -> None:
    """Statically validate one local plugin project without any discovery."""
    try:
        validate_plugin_project(project)
    except Exception:
        _plugin_error()
    typer.echo(json.dumps({"status": "VALID"}, ensure_ascii=True, separators=(",", ":")))


@plugin_app.command("test")
def plugin_test(project: Path = typer.Argument(...)) -> None:
    """Validate statically, resolve the one allow-listed plugin, never execute it."""
    try:
        contract = validate_plugin_project(project)
        discovered = discovery.discover_allowed_plugins([contract.id])
        if len(discovered) != 1:
            raise ValueError("plugin discovery must return exactly one plugin")
        plugin = discovered[0]
        if not isinstance(plugin, ToolPlugin):
            raise ValueError("discovered plugin must satisfy the ToolPlugin protocol")
        manifest = plugin.manifest
        if (
            manifest.id != contract.id
            or manifest.version != contract.version
            or manifest.kind != contract.kind
            or manifest.provides != contract.capabilities.provides
            or manifest.requires != contract.capabilities.requires
        ):
            raise ValueError("plugin manifest does not match the project contract")
        declared_schema = _normalize_json_schema(contract.input_schema)
        produced_schema = _normalize_json_schema(plugin.input_model.model_json_schema())
        if declared_schema != produced_schema:
            raise ValueError("plugin input_model schema does not match the project contract")
        registry = PluginRegistry([contract.id])
        registry.register(plugin)
        registry.resolve()
    except Exception:
        _plugin_error()
    typer.echo(json.dumps({"status": "PASS"}, ensure_ascii=True, separators=(",", ":")))


@app.callback()
def root() -> None:
    """VidSnap Harness command group."""


@app.command()
def analyze(
    video: Path = typer.Argument(..., exists=True, readable=True),
    goal: str = typer.Option("Summarize the video.", "--goal", min=1),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    runs_root: RunsRootOption = Path("run"),
    price_table: PriceTableOption = None,
) -> None:
    """Analyze one local video through the bounded evidence harness.

    The RunBundle goes to --output-dir, or to a new directory under the runs
    root; either way the finished run is appended to the run index.
    """
    prices = _load_prices(price_table)
    resolved_root = runs_root.expanduser().resolve()
    run_dir = output_dir if output_dir is not None else resolved_root / str(uuid.uuid4())
    result = asyncio.run(
        VideoHarness().run(
            VideoSource(path=video),
            VideoGoal(objective=goal),
            HarnessPolicy(output_dir=run_dir),
        )
    )
    _index_run(result.run_path, resolved_root, command="analyze", prices=prices)
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
    runs_root: RunsRootOption = Path("run"),
    price_table: PriceTableOption = None,
) -> None:
    """Produce the grounded interview record for one local video.

    The run's RunBundle is kept under the runs root whatever the outcome, its
    location is printed as run_path, and the run is appended to the run index.
    """
    prices = _load_prices(price_table)
    resolved_video = video.expanduser().resolve()
    resolved_output = output_dir.expanduser().resolve()
    resolved_root = runs_root.expanduser().resolve()
    run_dir = resolved_root / str(uuid.uuid4())
    result = asyncio.run(
        InterviewRecipeRunner().run(
            VideoSource(path=resolved_video), resolved_output, run_dir=run_dir
        )
    )
    _index_run(result.run_path, resolved_root, command="recipe interview", prices=prices)
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
    if result.run_path is not None:
        payload["run_path"] = str(result.run_path)
    typer.echo(json.dumps(payload, ensure_ascii=True))
    if not succeeded:
        raise typer.Exit(code=1)


@runs_app.command("list")
def runs_list(runs_root: RunsRootOption = Path("run")) -> None:
    """Print every indexed run, oldest first, with its latest review."""
    resolved_root = runs_root.expanduser().resolve()
    contents = read_index(resolved_root)
    if not any(record.get("record") == "run" for record in contents.records):
        typer.echo(f"No runs indexed in {resolved_root / INDEX_FILE_NAME}")
    else:
        typer.echo(render_run_table(contents.records))
    if contents.invalid_lines:
        typer.echo(f"Skipped {contents.invalid_lines} unreadable index line(s).", err=True)


@runs_app.command("review")
def runs_review(
    run: Annotated[
        str,
        typer.Argument(help="Run id, a unique run-id prefix (4+ characters), or a bundle path."),
    ],
    edit_minutes: Annotated[
        float | None,
        typer.Option("--edit-minutes", min=0, help="Minutes spent editing the output."),
    ] = None,
    published: Annotated[
        bool | None,
        typer.Option("--published/--not-published", help="Whether the output was published."),
    ] = None,
    factual_errors: Annotated[
        int | None,
        typer.Option("--factual-errors", min=0, help="Factual errors found in the output."),
    ] = None,
    images_replaced: Annotated[
        int | None,
        typer.Option("--images-replaced", min=0, help="Images replaced by hand."),
    ] = None,
    note: Annotated[str | None, typer.Option("--note", help="Free-text review note.")] = None,
    runs_root: RunsRootOption = Path("run"),
) -> None:
    """Append one human review of an indexed run; fields left out stay null."""
    try:
        review = RunReview(
            edit_minutes=edit_minutes,
            published=published,
            factual_errors=factual_errors,
            images_replaced=images_replaced,
            note=note,
        )
    except ValidationError as error:
        fields = sorted({str(item["loc"][0]) for item in error.errors() if item["loc"]})
        reason = (
            f"invalid {', '.join(fields)}" if fields else "a review must record at least one field"
        )
        typer.echo(f"Review refused: {reason}", err=True)
        raise typer.Exit(code=2) from None
    resolved_root = runs_root.expanduser().resolve()
    try:
        run_id = resolve_run_id(read_index(resolved_root).records, run)
    except LookupError as error:
        typer.echo(f"Review refused: {error.args[0]}", err=True)
        raise typer.Exit(code=2) from None
    index_path = append_index_record(resolved_root, review_record(run_id, review))
    typer.echo(
        json.dumps(
            {"status": "REVIEWED", "run_id": run_id, "index": str(index_path)},
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


@benchmark_app.command("evaluate")
def benchmark_evaluate(
    input_json: Annotated[
        Path,
        typer.Argument(
            metavar="INPUT_JSON",
            help="Trust evaluation input: sealed manifest and paired outcomes.",
        ),
    ],
    output: Annotated[Path, typer.Option("--output", help="Destination trust report JSON.")],
) -> None:
    """Evaluate trust metrics offline from one sealed manifest and its outcomes."""
    try:
        raw = input_json.read_text(encoding="utf-8")
        parsed = TrustEvaluationInput.model_validate(json.loads(raw))
        report = evaluate_trust(parsed.manifest, parsed.outcomes)
        destination = output.expanduser().resolve()
        text = json.dumps(
            report.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        destination.write_text(text + "\n", encoding="utf-8")
    except (ValueError, OSError) as error:
        typer.echo(f"benchmark evaluate refused: {type(error).__name__}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(
        json.dumps(
            {"status": "EVALUATED", "output": str(destination)},
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )


def main() -> None:
    """Run the VidSnap Harness command line application."""
    app()
