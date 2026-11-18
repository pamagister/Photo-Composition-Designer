"""Editor routes: slot assignment, removal, replacement and swapping."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.routes.projects import _canvas_response
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.project.editing import PageEditingService

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
    try:
        editing.assign_to_empty_slot(project_id, page_id, slot_id, photo_id)
    except ProjectError as error:
        return _error(project_id, str(error))
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
    try:
        editing.replace(project_id, page_id, slot_id, photo_id)
    except ProjectError as error:
        return _error(project_id, str(error))
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


@router.get("/projects/{project_id}/pages/{page_id}/unused")
def unused_pool_fragment(
    request: Request,
    project_id: int,
    page_id: int,
) -> HTMLResponse:
    """Return the unused-image panel fragment."""
    database = _open_database(request)
    editing = PageEditingService(database)
    photos = editing.unused_pool(project_id)
    context = {
        "request": request,
        "project_id": project_id,
        "page_id": page_id,
        "photos": photos,
    }
    return TEMPLATES.TemplateResponse(request, "partials/unused_pool.html", context)
