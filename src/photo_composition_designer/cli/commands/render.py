"""Render command: render project pages to PNG and optionally PDF."""

from __future__ import annotations

from pathlib import Path

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.export import ProjectExporter


def run(
    project_id: int,
    *,
    output_dir: Path | None = None,
    pdf: bool = True,
) -> int:
    """Render a project and write a PDF."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    exporter = ProjectExporter(database)
    target = output_dir or (data_dir() / "exports" / f"project_{project_id}")
    result = exporter.render_project(project_id, target, write_pdf=pdf)
    print(f"Rendered {len(result.rendered)} page(s) to {target}")
    if result.pdf_path is not None:
        print(f"PDF: {result.pdf_path}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    return 0
