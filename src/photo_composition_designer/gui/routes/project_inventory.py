"""Project inventory and source-root management routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    InventoryServiceDependency,
    ObjectDetectorDependency,
)
from photo_composition_designer.gui.routes.project_context import _error_redirect
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PhotoRepository,
)

router = APIRouter()


def _inventory_context(database: WorkspaceDatabase, project_id: int) -> dict[str, object]:
    """Build the legacy full-inventory fragment context."""
    connection = database.connect()
    photos = PhotoRepository(connection).list(project_id)
    assignments = AssignmentRepository(connection).list_by_project(project_id)
    return {
        "photos": photos,
        "assigned_ids": {assignment.photo_id for assignment in assignments},
    }


@router.get("/projects/{project_id}/inventory", response_class=HTMLResponse)
def inventory_fragment(
    request: Request,
    project_id: int,
    database: DatabaseDependency,
) -> HTMLResponse:
    """Return the current inventory fragment."""
    return TEMPLATES.TemplateResponse(
        request,
        "partials/inventory.html",
        _inventory_context(database, project_id),
    )


@router.post("/projects/{project_id}/source", response_class=HTMLResponse)
def add_source_root(
    project_id: int,
    inventory: InventoryServiceDependency,
    path: Annotated[str, Form()],
) -> RedirectResponse:
    """Add a validated local source directory to a project."""
    try:
        inventory.add_source_root(project_id, path)
    except ValueError as exc:
        return _error_redirect(project_id, str(exc))
    return RedirectResponse(f"/projects/{project_id}?added=1", status_code=303)


@router.get(
    "/projects/{project_id}/source/{source_root_id}/remap/preview",
    response_class=HTMLResponse,
)
def preview_source_remap(
    request: Request,
    project_id: int,
    source_root_id: int,
    inventory: InventoryServiceDependency,
    new_root: Annotated[str, Query()] = "",
) -> HTMLResponse:
    """Preview relinking a source root without mutating project state."""
    context: dict[str, object] = {
        "project_id": project_id,
        "source_root_id": source_root_id,
        "new_root": new_root.strip(),
        "preview": None,
        "error": "",
    }
    if not new_root.strip():
        context["error"] = "Enter a directory to relink this source root."
    else:
        try:
            context["preview"] = inventory.preview_remap(
                project_id,
                source_root_id=source_root_id,
                new_root=new_root,
            )
        except ValueError as exc:
            context["error"] = str(exc)
    return TEMPLATES.TemplateResponse(request, "partials/source_remap_preview.html", context)


@router.post("/projects/{project_id}/source/{source_root_id}/remap", response_class=HTMLResponse)
def remap_source_root(
    project_id: int,
    source_root_id: int,
    database: DatabaseDependency,
    inventory: InventoryServiceDependency,
    detector: ObjectDetectorDependency,
    new_root: Annotated[str, Form()],
) -> RedirectResponse:
    """Relink a source root to a new directory and rescan atomically."""
    try:
        inventory.apply_remap(project_id, source_root_id=source_root_id, new_root=new_root)
        PageEditingService(database, object_detector=detector).regenerate_auto_layouts(project_id)
    except ValueError as exc:
        return _error_redirect(project_id, str(exc))
    return RedirectResponse(f"/projects/{project_id}?remapped=1", status_code=303)


@router.post(
    "/projects/{project_id}/source/{source_root_id}/activate",
    response_class=HTMLResponse,
)
def activate_source_root(
    project_id: int,
    source_root_id: int,
    inventory: InventoryServiceDependency,
) -> RedirectResponse:
    """Make one source root the active scan target."""
    try:
        inventory.set_active_source_root(project_id, source_root_id)
    except ValueError as exc:
        return _error_redirect(project_id, str(exc))
    return RedirectResponse(f"/projects/{project_id}?activated=1", status_code=303)


@router.post(
    "/projects/{project_id}/source/{source_root_id}/remove",
    response_class=HTMLResponse,
)
def remove_source_root(
    project_id: int,
    source_root_id: int,
    inventory: InventoryServiceDependency,
) -> RedirectResponse:
    """Remove a source root that has no assigned photos."""
    try:
        inventory.remove_source_root(project_id, source_root_id)
    except ValueError as exc:
        return _error_redirect(project_id, str(exc))
    return RedirectResponse(f"/projects/{project_id}?removed=1", status_code=303)


@router.post("/projects/{project_id}/scan", response_model=None)
def scan_project(
    request: Request,
    project_id: int,
    database: DatabaseDependency,
    inventory: InventoryServiceDependency,
    detector: ObjectDetectorDependency,
) -> HTMLResponse | RedirectResponse:
    """Scan the active source root and return a summary fragment."""
    try:
        summary = inventory.scan(project_id)
        PageEditingService(database, object_detector=detector).regenerate_auto_layouts(project_id)
    except ValueError as exc:
        message = str(exc)
        if request.headers.get("HX-Request") == "true":
            return TEMPLATES.TemplateResponse(
                request,
                "partials/scan_result.html",
                {"summary": None, "error": message},
            )
        return _error_redirect(project_id, message)

    context = {
        "summary": summary,
        "error": "",
    }
    if request.headers.get("HX-Request") == "true":
        return TEMPLATES.TemplateResponse(request, "partials/scan_result_update.html", context)
    return RedirectResponse(f"/projects/{project_id}?scanned=1", status_code=303)


__all__ = ["router"]
