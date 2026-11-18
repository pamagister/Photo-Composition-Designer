"""Single Typer command-line application for Photo Composition Designer."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from photo_composition_designer.cli.commands import export as export_command
from photo_composition_designer.cli.commands import gui as gui_command
from photo_composition_designer.cli.commands import render as render_command

app = typer.Typer(
    help="Local-first calendar composition designer.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def callback() -> None:
    """Local-first calendar composition designer."""


@app.command()
def gui(
    host: Annotated[str, typer.Option(help="Host interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8767,
    log_level: Annotated[str, typer.Option(help="Uvicorn log level.")] = "info",
) -> None:
    """Start the local web editor."""
    raise typer.Exit(code=gui_command.run(host=host, port=port, log_level=log_level))


@app.command()
def render(
    project_id: Annotated[int, typer.Argument(help="Project ID to render.")],
    output_dir: Annotated[
        Path | None, typer.Option(help="Output directory for rendered pages.")
    ] = None,
    pdf: Annotated[bool, typer.Option(help="Also write a combined PDF.")] = True,
) -> None:
    """Render a project's pages to PNG and optionally PDF."""
    raise typer.Exit(code=render_command.run(project_id, output_dir=output_dir, pdf=pdf))


@app.command()
def export(
    project_id: Annotated[int, typer.Argument(help="Project ID to export.")],
    output_dir: Annotated[
        Path | None, typer.Option(help="Output directory for exported pages.")
    ] = None,
) -> None:
    """Export a project as rendered pages and a PDF."""
    raise typer.Exit(code=export_command.run(project_id, output_dir=output_dir))


def main() -> None:
    """Run the CLI."""
    app()


if __name__ == "__main__":
    main()
