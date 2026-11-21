"""Single Typer command-line application for Photo Composition Designer."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from photo_composition_designer.cli.commands import distribute as distribute_command
from photo_composition_designer.cli.commands import doctor as doctor_command
from photo_composition_designer.cli.commands import duplicate as duplicate_command
from photo_composition_designer.cli.commands import export as export_command
from photo_composition_designer.cli.commands import gui as gui_command
from photo_composition_designer.cli.commands import render as render_command
from photo_composition_designer.cli.commands import scan as scan_command

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
    open_browser: Annotated[
        bool,
        typer.Option("--open-browser", help="Open the web UI in the browser once it is ready."),
    ] = False,
) -> None:
    """Start the local web editor."""
    raise typer.Exit(
        code=gui_command.run(
            host=host,
            port=port,
            log_level=log_level,
            open_browser=open_browser,
        )
    )


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


@app.command()
def scan(
    project_id: Annotated[int, typer.Argument(help="Project ID to scan.")],
    source_root_id: Annotated[
        int | None, typer.Option(help="Specific source root ID; defaults to the active root.")
    ] = None,
) -> None:
    """Scan a project source directory and reconcile its photo inventory."""
    raise typer.Exit(code=scan_command.run(project_id, source_root_id=source_root_id))


@app.command()
def distribute(
    project_id: Annotated[int, typer.Argument(help="Project ID to distribute.")],
    strategy: Annotated[
        str, typer.Option(help="Distribution strategy: equal, random or date_aware.")
    ] = "equal",
    seed: Annotated[int | None, typer.Option(help="Random distribution seed.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview the proposal without applying it.")
    ] = False,
) -> None:
    """Preview or apply a photo distribution proposal."""
    raise typer.Exit(
        code=distribute_command.run(
            project_id,
            strategy=strategy,
            seed=seed,
            dry_run=dry_run,
        )
    )


@app.command()
def duplicate(
    project_id: Annotated[int, typer.Argument(help="Project ID to duplicate.")],
    name: Annotated[
        str | None, typer.Option(help="Name for the duplicate; defaults to the source name.")
    ] = None,
) -> None:
    """Duplicate a project within the workspace."""
    raise typer.Exit(code=duplicate_command.run(project_id, name=name))


@app.command()
def doctor() -> None:
    """Check workspace paths, schema, sources, photos and output profiles."""
    raise typer.Exit(code=doctor_command.run())


def cli_main() -> int:
    """Run the Typer command-line interface."""
    app()
    return 0
