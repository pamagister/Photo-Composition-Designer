"""Project selection, creation, source management and inventory routes."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.errors import ProjectError, ProjectNotFoundError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    InventoryServiceDependency,
    ProjectServiceDependency,
)
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.project.models import ProjectAggregate
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PageRepository,
    PhotoRepository,
)
from photo_composition_designer.project.services import ProjectService

router = APIRouter()


def _load_project(
    service: ProjectService,
    project_id: int,
) -> ProjectAggregate:
    """Load a project aggregate or raise a 404 response."""
    try:
        return service.open_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def _error_redirect(project_id: int, message: str) -> RedirectResponse:
    """Return to the project page with a visible error message."""
    return RedirectResponse(f"/projects/{project_id}?error={quote(message)}", status_code=303)


def _project_context(
    database: WorkspaceDatabase,
    aggregate: ProjectAggregate,
    *,
    selected_page_id: int | None = None,
    error: str = "",
    notice: str = "",
) -> dict[str, object]:
    """Build the template context for a project workspace page."""
    connection = database.connect()
    photos = PhotoRepository(connection).list(aggregate.project.id)
    assignments = AssignmentRepository(connection).list_by_project(aggregate.project.id)
    pages = aggregate.pages
    selected = (
        next((page for page in pages if page.id == selected_page_id), pages[0]) if pages else None
    )
    selected_assignments = (
        [assignment for assignment in assignments if assignment.page_id == selected.id]
        if selected
        else []
    )
    assigned_ids = {assignment.photo_id for assignment in assignments}
    source_states = [
        {"root": root, "exists": Path(root.path).is_dir()} for root in aggregate.source_roots
    ]
    return {
        "project": aggregate.project,
        "pages": pages,
        "selected_page": selected,
        "page": selected,
        "page_assignments": selected_assignments,
        "assignments": selected_assignments,
        "photos": photos,
        "photos_by_id": {photo.id: photo for photo in photos},
        "assigned_ids": assigned_ids,
        "source_states": source_states,
        "error": error,
        "notice": notice,
        "save_state": f"Saved {aggregate.project.updated_at[:19].replace('T', ' ')}",
    }


def _inventory_context(database: WorkspaceDatabase, project_id: int) -> dict[str, object]:
    """Build the template context for the inventory fragment."""
    connection = database.connect()
    photos = PhotoRepository(connection).list(project_id)
    assignments = AssignmentRepository(connection).list_by_project(project_id)
    return {
        "photos": photos,
        "assigned_ids": {assignment.photo_id for assignment in assignments},
    }


def _page_context(
    database: WorkspaceDatabase,
    project_id: int,
    page_id: int,
) -> dict[str, object] | None:
    """Build the template context for one page fragment."""
    connection = database.connect()
    page = PageRepository(connection).get(page_id)
    if page is None or page.project_id != project_id:
        return None
    assignments = list(AssignmentRepository(connection).list_by_page(page_id))
    photos = PhotoRepository(connection).list(project_id)
    return {
        "page": page,
        "assignments": assignments,
        "photos": photos,
        "photos_by_id": {photo.id: photo for photo in photos},
    }


@router.get("/projects", response_class=HTMLResponse)
def list_projects(
    request: Request,
    service: ProjectServiceDependency,
) -> HTMLResponse:
    """List all projects in the central workspace."""
    projects = service.list_projects()
    return TEMPLATES.TemplateResponse(
        request,
        "projects.html",
        {"projects": projects, "page_title": "Projects", "save_state": "Saved"},
    )


@router.get("/projects/new", response_class=HTMLResponse)
def new_project_form(request: Request) -> HTMLResponse:
    """Show the new-project form."""
    return TEMPLATES.TemplateResponse(
        request,
        "new_project.html",
        {"page_title": "New project", "save_state": "Unsaved", "error": "", "form": {}},
    )


@router.post("/projects", response_model=None)
def create_project(
    request: Request,
    service: ProjectServiceDependency,
    name: Annotated[str, Form()],
    page_count: Annotated[int, Form()],
    start_date: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    """Create a project with explicit weekly pages."""
    form = {"name": name, "page_count": page_count, "start_date": start_date}
    try:
        project = service.create_project(
            name=name,
            page_count=page_count,
            start_date=date.fromisoformat(start_date),
        )
    except (ValueError, ProjectError) as exc:
        return TEMPLATES.TemplateResponse(
            request,
            "new_project.html",
            {
                "page_title": "New project",
                "save_state": "Unsaved",
                "error": str(exc),
                "form": form,
            },
            status_code=400,
        )
    return RedirectResponse(f"/projects/{project.id}", status_code=303)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
    page: Annotated[int | None, Query(description="Selected page id.")] = None,
    error: str = "",
) -> HTMLResponse:
    """Show one project with its pages, source roots and photo inventory."""
    aggregate = _load_project(service, project_id)
    notice = ""
    if request.query_params.get("added") == "1":
        notice = "Source directory added."
    elif request.query_params.get("saved") == "1":
        notice = "Project name saved."
    elif request.query_params.get("scanned") == "1":
        notice = "Source directory scanned."
    context = _project_context(
        database,
        aggregate,
        selected_page_id=page,
        error=error,
        notice=notice,
    )
    return TEMPLATES.TemplateResponse(
        request,
        "project.html",
        {"page_title": aggregate.project.name, **context},
    )


@router.get("/projects/{project_id}/pages/{page_id}", response_class=HTMLResponse)
def project_page_fragment(
    request: Request,
    project_id: int,
    page_id: int,
    database: DatabaseDependency,
) -> HTMLResponse:
    """Return one page fragment for HTMX page navigation."""
    context = _page_context(database, project_id, page_id)
    if context is None:
        raise HTTPException(404, "page not found")
    return TEMPLATES.TemplateResponse(request, "partials/page_detail.html", context)


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


@router.post("/projects/{project_id}/scan", response_model=None)
def scan_project(
    request: Request,
    project_id: int,
    inventory: InventoryServiceDependency,
    database: DatabaseDependency,
) -> HTMLResponse | RedirectResponse:
    """Scan the active source root and return a summary fragment."""
    try:
        summary = inventory.scan(project_id)
    except ValueError as exc:
        message = str(exc)
        if request.headers.get("HX-Request") == "true":
            return TEMPLATES.TemplateResponse(
                request,
                "partials/scan_result.html",
                {"summary": None, "error": message, **_inventory_context(database, project_id)},
            )
        return _error_redirect(project_id, message)

    context = {
        "summary": summary,
        "error": "",
        **_inventory_context(database, project_id),
    }
    if request.headers.get("HX-Request") == "true":
        return TEMPLATES.TemplateResponse(request, "partials/scan_result_update.html", context)
    return RedirectResponse(f"/projects/{project_id}?scanned=1", status_code=303)


@router.post("/projects/{project_id}/rename", response_class=HTMLResponse)
def rename_project(
    project_id: int,
    service: ProjectServiceDependency,
    name: Annotated[str, Form()],
) -> RedirectResponse:
    """Rename a project and return to its workspace."""
    try:
        service.rename_project(project_id, name)
    except (ValueError, ProjectError) as exc:
        return _error_redirect(project_id, str(exc))
    return RedirectResponse(f"/projects/{project_id}?saved=1", status_code=303)


@router.get("/api/browse")
def browse_directories(path: str = "~") -> dict[str, object]:
    """List directories below a local path for the source-directory picker.

    Only directory names and paths are returned; file contents are never read.
    """
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.resolve()
    if not target.is_dir():
        raise HTTPException(400, "not a directory")
    try:
        directories = sorted(
            (item for item in target.iterdir() if item.is_dir()),
            key=lambda item: item.name.lower(),
        )
    except OSError as exc:
        raise HTTPException(400, f"cannot read directory: {exc}") from exc
    return {
        "path": str(target),
        "parent": None if target.parent == target else str(target.parent),
        "directories": [{"name": item.name, "path": str(item)} for item in directories],
    }
