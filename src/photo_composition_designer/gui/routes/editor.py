"""Editor routes: slot assignment, removal, replacement and swapping."""

from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.routes.projects import _canvas_response
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.rendering import ProjectRenderingService
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PageRepository,
    PhotoRepository,
)

router = APIRouter()


def _error(project_id: int, message: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/projects/{project_id}?error={message}",
        status_code=303,
    )


def _page_fragment(
    request: Request,
    project_id: int,
    page_id: int,
    message: str | None = None,
) -> HTMLResponse:
    database = _open_database(request)
    return _canvas_response(request, database, project_id, page_id, message or "")


def _open_database(request: Request) -> WorkspaceDatabase:
    return WorkspaceDatabase(request.app.state.settings.workspace_path())


def _has_unused_photos(database: WorkspaceDatabase, project_id: int) -> bool:
    """Return whether an available inventory photo has no assignment."""
    connection = database.connect()
    available = PhotoRepository(connection).list(project_id, available_only=True)
    used = {
        assignment.photo_id
        for assignment in AssignmentRepository(connection).list_by_project(project_id)
    }
    return any(photo.id not in used for photo in available)


def _render_project_previews(
    request: Request, database: WorkspaceDatabase, project_id: int
) -> None:
    """Render reduced previews for all pages after completing photo allocation."""
    settings = request.app.state.settings
    rendering = ProjectRenderingService(
        database,
        preview_dir=settings.preview_dir(),
        anniversaries_path=settings.anniversaries_path,
    )
    for page in PageRepository(database.connect()).list(project_id):
        rendering.render_preview(project_id, page.id, max_width=320)


@router.post("/projects/{project_id}/pages/{page_id}/assign")
def assign_photo(
    request: Request,
    project_id: int,
    page_id: int,
    slot_id: int = Form(...),
    photo_id: int = Form(...),
) -> HTMLResponse:
    """Assign a photo to an empty slot."""
    database = _open_database(request)
    editing = PageEditingService(database)
    had_unused_photos = _has_unused_photos(database, project_id)
    try:
        editing.assign_to_empty_slot(project_id, page_id, slot_id, photo_id)
    except ProjectError as error:
        return _error(project_id, str(error))
    if had_unused_photos and not _has_unused_photos(database, project_id):
        _render_project_previews(request, database, project_id)
    return _page_fragment(request, project_id, page_id, "Photo assigned.")


@router.post("/projects/{project_id}/pages/{page_id}/remove")
def remove_photo(
    request: Request,
    project_id: int,
    page_id: int,
    slot_id: int = Form(...),
) -> HTMLResponse:
    """Remove the photo from a slot and return it to the unused pool."""
    database = _open_database(request)
    editing = PageEditingService(database)
    editing.remove(project_id, page_id, slot_id)
    return _page_fragment(request, project_id, page_id, "Photo removed.")


@router.post("/projects/{project_id}/pages/{page_id}/replace")
def replace_photo(
    request: Request,
    project_id: int,
    page_id: int,
    slot_id: int = Form(...),
    photo_id: int = Form(...),
) -> HTMLResponse:
    """Replace the photo in an occupied slot."""
    database = _open_database(request)
    editing = PageEditingService(database)
    had_unused_photos = _has_unused_photos(database, project_id)
    try:
        editing.replace(project_id, page_id, slot_id, photo_id)
    except ProjectError as error:
        return _error(project_id, str(error))
    if had_unused_photos and not _has_unused_photos(database, project_id):
        _render_project_previews(request, database, project_id)
    return _page_fragment(request, project_id, page_id, "Photo replaced.")


@router.post("/projects/{project_id}/pages/{page_id}/swap")
def swap_photos(
    request: Request,
    project_id: int,
    page_id: int,
    slot_a: int = Form(...),
    slot_b: int = Form(...),
) -> HTMLResponse:
    """Swap the photos in two slots on the same page."""
    database = _open_database(request)
    editing = PageEditingService(database)
    editing.swap(project_id, page_id, slot_a, slot_b)
    return _page_fragment(request, project_id, page_id, "Photos swapped.")


@router.post("/projects/{project_id}/pages/{page_id}/crop")
def set_crop(
    request: Request,
    project_id: int,
    page_id: int,
    slot_id: int = Form(...),
    crop_zoom: float = Form(1.0),
    crop_focus_x: float = Form(0.5),
    crop_focus_y: float = Form(0.5),
) -> HTMLResponse:
    """Update the crop zoom and focal point for one assigned slot."""
    database = _open_database(request)
    editing = PageEditingService(database)
    try:
        editing.set_crop(
            project_id,
            page_id,
            slot_id,
            crop_zoom=crop_zoom,
            crop_focus_x=crop_focus_x,
            crop_focus_y=crop_focus_y,
        )
    except ProjectError as error:
        return _error(project_id, str(error))
    return _page_fragment(request, project_id, page_id, "Crop updated.")


@router.post("/projects/{project_id}/pages/{page_id}/description")
def update_description(
    request: Request,
    project_id: int,
    page_id: int,
    description: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Update the page description."""
    database = _open_database(request)
    editing = PageEditingService(database)
    try:
        editing.set_description(project_id, page_id, description)
    except ProjectError as error:
        return _error(project_id, str(error))
    return _page_fragment(request, project_id, page_id, "Description saved.")


@router.post("/projects/{project_id}/pages/{page_id}/overrides")
def set_page_overrides(
    request: Request,
    project_id: int,
    page_id: int,
    hide_local_map: Annotated[str, Form()] = "",
    hide_calendar_strip: Annotated[str, Form()] = "",
    hide_description: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Set the per-page overrides for map, calendar strip and description."""
    database = _open_database(request)
    editing = PageEditingService(database)
    hidden = {"1", "on", "true", "yes"}
    try:
        editing.set_local_overrides(
            project_id,
            page_id,
            hide_local_map=hide_local_map.strip().lower() in hidden,
            hide_calendar_strip=hide_calendar_strip.strip().lower() in hidden,
            hide_description=hide_description.strip().lower() in hidden,
        )
    except ProjectError as error:
        return _error(project_id, str(error))
    return _page_fragment(request, project_id, page_id, "Page overrides saved.")


@router.get("/projects/{project_id}/pages/{page_id}/unused")
def unused_pool_fragment(
    request: Request,
    project_id: int,
    page_id: int,
    filter: str = "unused",
) -> HTMLResponse:
    """Return the filterable project photo strip."""
    database = _open_database(request)
    connection = database.connect()
    page = PageRepository(connection).get(page_id)
    if page is None or page.project_id != project_id:
        raise HTTPException(404, "page not found")
    photos = PhotoRepository(connection).list(project_id)
    usage_counts = Counter(
        assignment.photo_id
        for assignment in AssignmentRepository(connection).list_by_project(project_id)
    )
    selected_filter = "all" if filter == "all" else "unused"
    if selected_filter == "unused":
        photos = [
            photo for photo in photos if photo.available and usage_counts.get(photo.id, 0) == 0
        ]
    context = {
        "request": request,
        "project_id": project_id,
        "page_id": page_id,
        "photos": photos,
        "usage_counts": usage_counts,
        "photo_filter": selected_filter,
    }
    return TEMPLATES.TemplateResponse(request, "partials/unused_pool.html", context)
