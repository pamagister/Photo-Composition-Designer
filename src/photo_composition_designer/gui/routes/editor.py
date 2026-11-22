"""Editor routes: slot assignment, removal, replacement and swapping."""

from __future__ import annotations

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.dependencies import ObjectDetectorDependency
from photo_composition_designer.gui.routes.project_context import _canvas_response
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PageRepository,
    PhotoRepository,
)
from photo_composition_designer.render.object_detector import ObjectDetector

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
    request: Request,
    database: WorkspaceDatabase,
    project_id: int,
    object_detector: ObjectDetector | None = None,
) -> None:
    """Enqueue reduced previews for all pages after completing photo allocation.

    Jobs are submitted to the background worker with background priority
    so the request returns promptly. The worker coalesces duplicates and
    renders off the request thread.
    """
    del object_detector  # The worker uses the detector configured at startup.
    worker = getattr(request.app.state, "preview_worker", None)
    if worker is None:
        return
    for page in PageRepository(database.connect()).list(project_id):
        worker.submit(project_id, page.id, max_width=200, priority=1)


@router.post("/projects/{project_id}/pages/{page_id}/assign")
def assign_photo(
    request: Request,
    project_id: int,
    page_id: int,
    detector: ObjectDetectorDependency,
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
        _render_project_previews(request, database, project_id, detector)
    return _page_fragment(request, project_id, page_id, "Photo assigned.")


@router.post("/projects/{project_id}/pages/{page_id}/populate")
def populate_page(
    request: Request,
    project_id: int,
    page_id: int,
) -> HTMLResponse:
    """Fill empty slots with unused photos in inventory order."""
    database = _open_database(request)
    editing = PageEditingService(database)
    try:
        assigned = editing.populate(project_id, page_id)
    except ProjectError as error:
        return _error(project_id, str(error))
    if assigned:
        message = f"Populated {assigned} slot(s)."
    else:
        message = "No empty slots or no unused photos to fill."
    return _page_fragment(request, project_id, page_id, message)


@router.post("/projects/{project_id}/pages/{page_id}/assign-selected")
def assign_selected_photos(
    request: Request,
    project_id: int,
    page_id: int,
    detector: ObjectDetectorDependency,
    photo_id: Annotated[list[int], Form()],
    slot_id: int | None = Form(None),
) -> HTMLResponse:
    """Assign the selected unused photos to the page's empty slots in order.

    ``photo_id`` is a repeated form field carrying the selected photo ids in the
    order the user checked them. When ``slot_id`` is provided, the first
    eligible photo is assigned there before filling remaining empty slots.
    Automatic pages ignore ``slot_id`` and add every selected photo, filling
    empty slots first and reflowing once when more photos are selected than
    there are holes.
    """
    database = _open_database(request)
    editing = PageEditingService(database, object_detector=detector)
    try:
        if editing.uses_auto_layout(project_id, page_id):
            added, regenerated = editing.auto_add_many(project_id, page_id, photo_id)
            if added == 0:
                message = "No empty slots or no selected photos to assign."
            elif added == 1:
                message = "Added 1 photo and layout reflowed." if regenerated else "Added 1 photo."
            else:
                message = (
                    f"Added {added} photos and layout reflowed."
                    if regenerated
                    else f"Added {added} photos."
                )
        else:
            assigned = editing.assign_selected(project_id, page_id, photo_id, slot_id=slot_id)
            if assigned:
                message = f"Assigned {assigned} photo(s)."
            else:
                message = "No empty slots or no selected photos to assign."
    except ProjectError as error:
        return _error(project_id, str(error))
    return _page_fragment(request, project_id, page_id, message)


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


@router.post("/projects/{project_id}/pages/{page_id}/auto/add")
def auto_add_photo(
    request: Request,
    project_id: int,
    page_id: int,
    detector: ObjectDetectorDependency,
    photo_id: Annotated[list[int], Form()],
) -> HTMLResponse:
    """Add one or more photos to an automatic page.

    Empty slots are filled first. When the page has no empty slot left, the
    grid is regenerated once for all remaining photos.
    """
    database = _open_database(request)
    editing = PageEditingService(database, object_detector=detector)
    had_unused_photos = _has_unused_photos(database, project_id)
    try:
        added, regenerated = editing.auto_add_many(project_id, page_id, photo_id)
    except ProjectError as error:
        return _error(project_id, str(error))
    if had_unused_photos and not _has_unused_photos(database, project_id):
        _render_project_previews(request, database, project_id, detector)
    if added == 0:
        message = "No photos added."
    elif added == 1:
        message = "Photo added and layout reflowed." if regenerated else "Photo added."
    else:
        message = (
            f"{added} photos added and layout reflowed."
            if regenerated
            else f"{added} photos added."
        )
    return _page_fragment(request, project_id, page_id, message)


@router.post("/projects/{project_id}/pages/{page_id}/auto/reflow")
def auto_reflow_page(
    request: Request,
    project_id: int,
    page_id: int,
    detector: ObjectDetectorDependency,
) -> HTMLResponse:
    """Rebuild an automatic layout with one slot per assigned photo."""
    database = _open_database(request)
    editing = PageEditingService(database, object_detector=detector)
    try:
        changed = editing.auto_reflow(project_id, page_id)
    except ProjectError as error:
        return _error(project_id, str(error))
    message = "Layout reflowed." if changed else "This page does not use the automatic layout."
    return _page_fragment(request, project_id, page_id, message)


@router.post("/projects/{project_id}/pages/{page_id}/auto/remove-empty")
def auto_remove_empty_slots(
    request: Request,
    project_id: int,
    page_id: int,
    detector: ObjectDetectorDependency,
) -> HTMLResponse:
    """Drop empty slots from an automatic layout."""
    database = _open_database(request)
    editing = PageEditingService(database, object_detector=detector)
    try:
        changed = editing.auto_remove_empty(project_id, page_id)
    except ProjectError as error:
        return _error(project_id, str(error))
    message = "Empty slots removed." if changed else "No empty slots to remove."
    return _page_fragment(request, project_id, page_id, message)


@router.post("/projects/{project_id}/pages/{page_id}/assignments/clear")
def clear_page_assignments(
    request: Request,
    project_id: int,
    page_id: int,
) -> HTMLResponse:
    """Remove every assignment from one page and keep its layout."""
    database = _open_database(request)
    editing = PageEditingService(database)
    try:
        removed = editing.clear_page_assignments(project_id, page_id)
    except ProjectError as error:
        return _error(project_id, str(error))
    if removed:
        message = f"Removed {removed} assignment(s)."
    else:
        message = "No assignments to remove."
    return _page_fragment(request, project_id, page_id, message)


@router.post("/projects/{project_id}/assignments/clear")
def clear_project_assignments(
    request: Request,
    project_id: int,
) -> RedirectResponse:
    """Remove every assignment in a project and return to the project page."""
    database = _open_database(request)
    editing = PageEditingService(database)
    try:
        editing.clear_project_assignments(project_id)
    except ProjectError as error:
        return _error(project_id, str(error))
    _render_project_previews(request, database, project_id)
    return RedirectResponse(f"/projects/{project_id}?assignments=1", status_code=303)


@router.post("/projects/{project_id}/pages/{page_id}/replace")
def replace_photo(
    request: Request,
    project_id: int,
    page_id: int,
    detector: ObjectDetectorDependency,
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
        _render_project_previews(request, database, project_id, detector)
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


@router.post("/projects/{project_id}/pages/{page_id}/crop/live")
def set_crop_live(
    request: Request,
    project_id: int,
    page_id: int,
    slot_id: int = Form(...),
    crop_zoom: float = Form(1.0),
    crop_focus_x: float = Form(0.5),
    crop_focus_y: float = Form(0.5),
) -> Response:
    """Persist a keyboard crop adjustment and return the new page revision.

    This lightweight endpoint backs the arrow-key crop path. It clamps the
    incoming values into range, persists them and returns ``204`` with the new
    revision in ``X-Page-Revision`` plus an ``HX-Trigger: pcd:crop-updated``
    header so the client can refresh the preview image without a full canvas
    re-render.

    A high-priority preview job is enqueued so the background worker
    re-renders the page at the new revision; the client polls the preview
    endpoint until the new bytes are available.
    """
    database = _open_database(request)
    editing = PageEditingService(database)
    clamped_zoom = min(3.0, max(1.0, crop_zoom))
    clamped_x = min(1.0, max(0.0, crop_focus_x))
    clamped_y = min(1.0, max(0.0, crop_focus_y))
    try:
        editing.set_crop(
            project_id,
            page_id,
            slot_id,
            crop_zoom=clamped_zoom,
            crop_focus_x=clamped_x,
            crop_focus_y=clamped_y,
        )
    except ProjectError as error:
        return _error(project_id, str(error))
    worker = getattr(request.app.state, "preview_worker", None)
    if worker is not None:
        worker.submit(project_id, page_id, max_width=800, priority=0)
    with database.connect() as connection:
        page = PageRepository(connection).get(page_id)
        revision = page.render_revision if page is not None else 0
    return Response(
        status_code=204,
        headers={
            "X-Page-Revision": str(revision),
            "HX-Trigger": "pcd:crop-updated",
        },
    )


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
    center_description: Annotated[str, Form()] = "",
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
            center_description=(True if center_description.strip().lower() in hidden else None),
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
