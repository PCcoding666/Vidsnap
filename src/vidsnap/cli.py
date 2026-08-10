"""Command-line entry point for VidSnap Harness."""

import typer

app = typer.Typer(
    name="vidsnap",
    help="VidSnap Harness: evidence-grounded video analysis.",
    no_args_is_help=True,
)


@app.callback()
def root() -> None:
    """VidSnap Harness command group."""


def main() -> None:
    """Run the VidSnap Harness command line application."""
    app()
