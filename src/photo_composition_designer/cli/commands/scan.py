"""Scan command: reconcile a project's source inventory."""

from __future__ import annotations

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.core.locations import Locations
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.settings import load_gui_settings
from photo_composition_designer.project.inventory import InventoryService


def run(project_id: int, *, source_root_id: int | None = None) -> int:
    """Scan one source root and print the reconciliation summary."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        settings = load_gui_settings()
        summary = InventoryService(
            database,
            locations=Locations.with_overrides(settings.locations_path),
        ).scan(
            project_id,
            source_root_id=source_root_id,
        )
    except (ValueError, ProjectError) as exc:
        print(f"error: {exc}")
        return 1
    finally:
        database.close()

    print(
        f"Scanned {summary.source_path}: discovered {summary.discovered}, "
        f"added {summary.added}, updated {summary.updated}, "
        f"unavailable {summary.unavailable} in {summary.duration_seconds:.2f}s"
    )
    print(f"Symlink policy: {summary.symlink_policy}")
    for warning in summary.warnings:
        print(f"warning: {warning}")
    return 0
