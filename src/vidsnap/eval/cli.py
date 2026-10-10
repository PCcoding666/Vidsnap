"""``vidsnap eval``: validate eval sets, run systems, report, and blind human review."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from vidsnap.eval.costs import load_eval_prices
from vidsnap.eval.providers import ENDPOINTS, EndpointName
from vidsnap.eval.report import build_report, load_human, load_results
from vidsnap.eval.review import build_review, import_scores
from vidsnap.eval.runner import RunOptions, live_system_needs_budget, run_suite
from vidsnap.eval.suite import LoadedSuite, default_media_root, load_suite, validate_suite
from vidsnap.eval.systems import BuildOptions, list_systems, parse_system

eval_app = typer.Typer(
    help="Evaluate task outputs: harness + model vs native video models (docs/eval.md)."
)
review_app = typer.Typer(help="Blind A/B human review of two systems' outputs.")
eval_app.add_typer(review_app, name="review")

SuitesDirOption = Annotated[
    Path | None, typer.Option("--suites-dir", help="Directory of suite files.")
]
MediaRootOption = Annotated[
    Path | None,
    typer.Option(
        "--media-root",
        help="Root for item media paths; default VIDSNAP_EVAL_MEDIA_ROOT or <suites>/../media.",
    ),
]


@eval_app.command("validate")
def eval_validate(
    suite: Annotated[str, typer.Argument(help="Suite name (t1, t2a, t2b, t3) or file.")],
    suites_dir: SuitesDirOption = None,
    media_root: MediaRootOption = None,
    hashes: Annotated[bool, typer.Option("--hashes/--no-hashes")] = True,
) -> None:
    """Check one suite: format, references, placeholders and local media."""
    loaded = load_suite_or_exit(suite, suites_dir)
    root = media_root or default_media_root(loaded.path)
    issues = validate_suite(loaded, root, check_hashes=hashes)
    counts = {status: 0 for status in ("ready", "needs_reference", "placeholder")}
    for item in loaded.suite.items:
        counts[item.status] += 1
    typer.echo(
        f"{loaded.suite.suite_id} ({loaded.suite.task}): {len(loaded.suite.items)} items, "
        + ", ".join(f"{name} {count}" for name, count in counts.items())
    )
    for issue in issues:
        typer.echo(f"{issue.level.upper():7} {issue.item_id or '-':24} {issue.message}")
    if any(issue.level == "error" for issue in issues):
        raise typer.Exit(code=1)


def load_suite_or_exit(suite: str, suites_dir: Path | None) -> LoadedSuite:
    try:
        return load_suite(suite, suites_dir)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from None


@eval_app.command("systems")
def eval_systems() -> None:
    """List the allow-listed systems and harness modifiers."""
    for name in list_systems():
        typer.echo(name)
    typer.echo("harness modifiers: +oracle-asr, +oracle-frames, +frame-labels")


@eval_app.command("run")
def eval_run(
    suite: Annotated[str, typer.Option("--suite", help="Suite name or file.")],
    system: Annotated[str, typer.Option("--system", help="See `vidsnap eval systems`.")],
    items: Annotated[str | None, typer.Option("--items", help="Comma-separated item ids.")] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    suites_dir: SuitesDirOption = None,
    media_root: MediaRootOption = None,
    media_mode: Annotated[
        str, typer.Option("--media-mode", help="real, or fake (mock systems only).")
    ] = "real",
    runs_root: Annotated[
        Path, typer.Option("--runs-root", envvar="VIDSNAP_RUNS_ROOT", help="RunBundles + index.")
    ] = Path("run"),
    out: Annotated[Path, typer.Option("--out", help="Results and rendered outputs.")] = Path(
        "eval-out"
    ),
    price_table: Annotated[
        Path | None,
        typer.Option("--price-table", help="vidsnap.eval-price-table/v1 file (required live)."),
    ] = None,
    max_cost: Annotated[
        float | None,
        typer.Option("--max-cost", min=0, help="Stop once measured cost reaches this (live)."),
    ] = None,
    endpoint: Annotated[str, typer.Option("--endpoint", help="dashscope or token-plan.")] = (
        "dashscope"
    ),
    timeout: Annotated[float, typer.Option("--timeout", min=10, max=900)] = 300.0,
    render_check: Annotated[
        bool, typer.Option("--render-check", help="Headless-render HTML (needs Chrome).")
    ] = False,
) -> None:
    """Run one suite against one system; every item is a traced RunBundle."""
    try:
        spec = parse_system(system)
    except ValueError as error:
        typer.echo(f"System refused: {error}", err=True)
        raise typer.Exit(code=2) from None
    if media_mode not in ("real", "fake"):
        typer.echo("--media-mode must be real or fake", err=True)
        raise typer.Exit(code=2)
    if media_mode == "fake" and not spec.mock:
        typer.echo("--media-mode fake is only for mock systems", err=True)
        raise typer.Exit(code=2)
    if endpoint not in ENDPOINTS:
        typer.echo("--endpoint must be dashscope or token-plan", err=True)
        raise typer.Exit(code=2)
    prices = None
    if price_table is not None:
        try:
            prices = load_eval_prices(price_table.expanduser())
        except ValueError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=2) from None
    if live_system_needs_budget(spec) and (prices is None or max_cost is None):
        typer.echo("Live systems need --price-table and --max-cost (spending cap).", err=True)
        raise typer.Exit(code=2)
    loaded = load_suite_or_exit(suite, suites_dir)
    selected = tuple(part.strip() for part in items.split(",") if part.strip()) if items else None
    options = RunOptions(
        suite=loaded,
        system=spec,
        media_root=(media_root or default_media_root(loaded.path)).expanduser(),
        runs_root=runs_root.expanduser(),
        out_dir=out.expanduser(),
        item_ids=selected,
        limit=limit,
        prices=prices,
        max_cost=max_cost,
        media_mode=_media_mode(media_mode),
        render_check=render_check,
        build=BuildOptions(endpoint=_endpoint(endpoint), timeout_seconds=timeout),
        progress=lambda message: typer.echo(message, err=True),
    )
    try:
        path, document = asyncio.run(run_suite(options))
    except ValueError as error:
        typer.echo(f"Eval run refused: {error}", err=True)
        raise typer.Exit(code=2) from None
    items_out = document.get("items")
    count = len(items_out) if isinstance(items_out, list) else 0
    typer.echo(
        json.dumps(
            {
                "results": str(path),
                "items": count,
                "spent": document.get("spent"),
                "currency": document.get("currency"),
                "stopped_reason": document.get("stopped_reason"),
            },
            ensure_ascii=True,
        )
    )


def _media_mode(value: str) -> Literal["real", "fake"]:
    return "fake" if value == "fake" else "real"


def _endpoint(value: str) -> EndpointName:
    return "token-plan" if value == "token-plan" else "dashscope"


@eval_app.command("report")
def eval_report(
    results: Annotated[list[Path], typer.Argument(help="vidsnap.eval-result/v1 files.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Markdown report path.")],
    human: Annotated[
        list[Path] | None, typer.Option("--human", help="vidsnap.eval-human/v1 files.")
    ] = None,
    estimate: Annotated[
        bool, typer.Option("--estimate", help="Add estimated full-run cost (needs prices).")
    ] = False,
    price_table: Annotated[Path | None, typer.Option("--price-table")] = None,
    suites_dir: SuitesDirOption = None,
) -> None:
    """Aggregate result files into one Markdown comparison report."""
    try:
        documents = load_results(results)
        scores = load_human(human or [])
        prices = load_eval_prices(price_table.expanduser()) if price_table else None
    except (ValueError, OSError) as error:
        typer.echo(f"Report refused: {error}", err=True)
        raise typer.Exit(code=2) from None
    if estimate and prices is None:
        typer.echo("--estimate needs --price-table", err=True)
        raise typer.Exit(code=2)
    suites = []
    if estimate:
        for task in ("t1", "t2a", "t2b", "t3"):
            suites.append(load_suite_or_exit(task, suites_dir))
    text = build_report(documents, scores, suites=suites, prices=prices if estimate else None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    typer.echo(str(output))


@review_app.command("build")
def review_build(
    a: Annotated[Path, typer.Option("--a", help="First system's result file.")],
    b: Annotated[Path, typer.Option("--b", help="Second system's result file.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Review page (HTML).")],
    key: Annotated[Path, typer.Option("--key", help="Where to write the A/B key (keep private).")],
    seed: Annotated[int | None, typer.Option("--seed")] = None,
) -> None:
    """Write a blind A/B review page and its separate key file."""
    try:
        documents = load_results([a, b])
        count, review_id = build_review(documents[0], documents[1], output, key, seed=seed)
    except (ValueError, OSError, KeyError) as error:
        typer.echo(f"Review refused: {error}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(
        json.dumps({"page": str(output), "key": str(key), "pairs": count, "review": review_id})
    )


@review_app.command("import")
def review_import(
    scores: Annotated[Path, typer.Argument(help="Scores JSON exported from the review page.")],
    key: Annotated[Path, typer.Option("--key", help="The review's key file.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="vidsnap.eval-human/v1 file.")],
) -> None:
    """Un-blind exported scores into a human score file for `vidsnap eval report`."""
    try:
        human = import_scores(
            json.loads(scores.read_text(encoding="utf-8")),
            json.loads(key.read_text(encoding="utf-8")),
        )
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        typer.echo(f"Import refused: {error}", err=True)
        raise typer.Exit(code=2) from None
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(human.model_dump_json(indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps({"output": str(output), "scores": len(human.scores)}))
