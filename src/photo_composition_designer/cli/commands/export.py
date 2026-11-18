"""Export command: render project pages and write a PDF."""

from __future__ import annotations

from pathlib import Path

from photo_composition_designer.cli.commands.render import run as render_run


def run(
    project_id: int,
    *,
    output_dir: Path | None = None,
) -> int:
    """Export a project as rendered pages and a PDF."""
    return render_run(project_id, output_dir=output_dir, pdf=True)
