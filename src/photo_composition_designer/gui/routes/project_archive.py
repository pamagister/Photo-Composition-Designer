"""Import and export routes for reference-only `.pcd` project archives."""

from __future__ import annotations

import sqlite3
from html import escape
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response

from photo_composition_designer.core.errors import ProjectNotFoundError
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    ProjectServiceDependency,
)
from photo_composition_designer.io.project_archive import (
    MAX_ARCHIVE_SIZE,
    export_project_archive,
    import_project_archive,
)

router = APIRouter()


@router.get("/projects/{project_id}/archive")
def export_pcd(
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
) -> Response:
    """Download a project archive without including photo files."""
    try:
        project = service.get_project(project_id)
        archive = export_project_archive(database, project_id)
    except ProjectNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    filename = quote(f"{project.name}.pcd")
    return Response(
        archive,
        media_type="application/vnd.photo-composition-designer",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/projects/import-pcd", response_model=None)
async def import_pcd(
    database: DatabaseDependency,
    archive: Annotated[UploadFile, File()],
) -> RedirectResponse | Response:
    """Import a reference-only `.pcd` archive as a new project."""
    if not archive.filename or not archive.filename.lower().endswith(".pcd"):
        return Response("Choose a .pcd project archive.", status_code=400, media_type="text/plain")
    contents = await archive.read(MAX_ARCHIVE_SIZE + 1)
    if len(contents) > MAX_ARCHIVE_SIZE:
        return Response("Project archive exceeds the size limit.", status_code=413)
    try:
        project = import_project_archive(database, contents)
    except (ValueError, KeyError, TypeError, OverflowError, sqlite3.Error) as error:
        return Response(
            f"Project archive could not be imported: {escape(str(error))}",
            status_code=400,
            media_type="text/html",
        )
    return RedirectResponse(f"/projects/{project.id}", status_code=303)


__all__ = ["router"]
