"""Single Typer command-line application for Photo Composition Designer."""

from __future__ import annotations

from typing import Annotated

import typer

from photo_composition_designer.cli.commands import gui as gui_command

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


def main() -> None:
    """Run the CLI."""
    app()


if __name__ == "__main__":
    main()
