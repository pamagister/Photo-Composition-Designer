"""Duplicate command: copy a project within the workspace."""

from __future__ import annotations

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.services import ProjectService


def run(project_id: int, *, name: str | None = None) -> int:
    """Duplicate a project and print the new project identity."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    service = ProjectService(database)
    try:
        duplicate = service.duplicate_project(project_id, name=name)
    except (ValueError, ProjectError) as exc:
        print(f"error: {exc}")
        return 1
    finally:
        database.close()

    print(f"Duplicated project {project_id} as {duplicate.id}: {duplicate.name}")
    return 0
