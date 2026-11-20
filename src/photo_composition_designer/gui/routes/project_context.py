"""Shared project context and page-fragment helpers.

These helpers build the template contexts for the project workspace, editor
canvas and page thumbnails. They are shared by the focused route modules so
the route handlers stay thin.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.errors import ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.io.media import resolve_source_path
from photo_composition_designer.layouts.loader import load_catalogue
from photo_composition_designer.project.models import (
    PhotoAsset,
    ProjectAggregate,
    SourceRoot,
)
from photo_composition_designer.project.rendering import (
    ProjectRenderingService,
    preview_cache_key_for,
    profile_from_project,
)
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
)
from photo_composition_designer.project.services import ProjectService
from photo_composition_designer.render.layout_geometry import (
    compute_collage_box,
    slot_overlay_rectangles,
)
from photo_composition_designer.render.object_detector import ObjectDetector
from photo_composition_designer.render.page import PageRenderInput


def _load_project(
    service: ProjectService,
    project_id: int,
) -> ProjectAggregate:
    """Load a project aggregate or raise a 404 response."""
    try:
        return service.open_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def _collage_box_for_page(page, profile):
    """Return the collage content box for a page using the shared geometry."""
    render_input = PageRenderInput(
        page_date=date.fromisoformat(page.start_date),
        description=page.description,
        layout=None,
        output_profile=profile,
        title=profile.calendar.title,
        title_page=profile.calendar.use_title_page and page.page_index == 0,
        hide_local_map=page.hide_local_map,
        hide_calendar_strip=page.hide_calendar_strip,
        hide_description=page.hide_description,
        center_description=page.center_description,
    )
    return compute_collage_box(render_input, profile)


def _slot_overlay_data(page, profile, slots, slot_assignment_map):
    """Build per-slot overlay rectangles (page percentages) for the preview."""
    if not slots:
        return []
    box = _collage_box_for_page(page, profile)
    occupied = set(slot_assignment_map)
    overlays = []
    for rect in slot_overlay_rectangles(slots, box):
        assignment = slot_assignment_map.get(rect.slot_id)
        overlays.append(
            {
                "slot_id": rect.slot_id,
                "slot_key": rect.slot_key,
                "occupied": rect.slot_id in occupied,
                "photo_id": assignment.photo_id if assignment is not None else None,
                "left": round(rect.left, 4),
                "top": round(rect.top, 4),
                "width": round(rect.width, 4),
                "height": round(rect.height, 4),
            }
        )
    return overlays


def _error_redirect(project_id: int, message: str) -> RedirectResponse:
    """Return to the project page with a visible error message."""
    return RedirectResponse(f"/projects/{project_id}?error={quote(message)}", status_code=303)


def _submit_detection_warmups(
    request: Request,
    project_id: int,
    available_photos: list[PhotoAsset],
    source_roots: list[SourceRoot],
    detector: ObjectDetector | None,
) -> None:
    """Enqueue low-priority detection warm-ups for available project photos.

    Warm-up is skipped when object-aware cropping is disabled or the model is
    unavailable. Jobs run at the lowest worker priority, so they never delay
    the visible-page preview. The worker coalesces repeated identities, which
    makes repeated project page loads idempotent.
    """
    if detector is None:
        return
    worker = getattr(request.app.state, "preview_worker", None)
    submit_warmup = getattr(worker, "submit_warmup", None)
    if submit_warmup is None:
        return

    roots = {root.id: root for root in source_roots}
    for photo in available_photos:
        root = roots.get(photo.source_root_id)
        if root is None:
            continue
        try:
            path = resolve_source_path(root.path, photo.relative_path)
        except ValueError:
            continue
        if not path.is_file():
            continue
        identity = (int(photo.mtime or 0), int(photo.file_size or 0))
        submit_warmup(project_id, path, identity=identity)


def _project_context(
    database: WorkspaceDatabase,
    aggregate: ProjectAggregate,
    *,
    selected_page_id: int | None = None,
    photo_filter: str = "unused",
    error: str = "",
    notice: str = "",
    settings: GuiSettings | None = None,
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
    profile = profile_from_project(aggregate.project)
    title_page = (
        profile.calendar.use_title_page and selected is not None and selected.page_index == 0
    )
    usage_counts = Counter(assignment.photo_id for assignment in assignments)
    assigned_ids = set(usage_counts)
    unused_photos = [photo for photo in photos if photo.id not in assigned_ids]
    available_photos = [photo for photo in photos if photo.available]
    source_states = [
        {"root": root, "exists": Path(root.path).is_dir()} for root in aggregate.source_roots
    ]
    from photo_composition_designer.project.repositories import LayoutRepository

    layout_repo = LayoutRepository(connection)
    slots: list = []
    slot_count = 0
    slot_assignment_map: dict = {}
    current_layout_key = ""
    if selected is not None and selected.layout_id is not None:
        layout = layout_repo.get_by_id(selected.layout_id)
        if layout is not None:
            slots = list(layout.slots)
            slot_count = len(slots)
            current_layout_key = layout.key
            slot_assignment_map = {
                assignment.slot_id: assignment for assignment in selected_assignments
            }

    # Per-page thumbnail hints: the description is rendered but empty, and not
    # every slot holds a photo. Slot counts are cached per layout id.
    layout_slot_cache: dict[int, int] = {}
    assignments_by_page = Counter(assignment.page_id for assignment in assignments)
    page_status: dict[int, dict[str, bool]] = {}
    for pg in pages:
        total_slots = 0
        if pg.layout_id is not None:
            if pg.layout_id not in layout_slot_cache:
                pg_layout = layout_repo.get_by_id(pg.layout_id)
                layout_slot_cache[pg.layout_id] = len(pg_layout.slots) if pg_layout else 0
            total_slots = layout_slot_cache[pg.layout_id]
        filled_slots = assignments_by_page.get(pg.id, 0)
        page_status[pg.id] = {
            "description_missing": bool(
                profile.layout.use_photo_description
                and not pg.hide_description
                and not pg.description
            ),
            "incomplete": total_slots > 0 and filled_slots < total_slots,
        }

    # Immutable preview asset URLs for the sidebar thumbnails. The key is
    # derived from the same render inputs the preview renderer uses, so a
    # new revision produces a new URL and the browser can cache forever.
    thumb_cache_keys: dict[int, str] = {}
    if settings is not None and pages:
        rendering = ProjectRenderingService(
            database,
            anniversaries_path=settings.anniversaries_path,
        )
        for pg in pages:
            key = preview_cache_key_for(rendering, connection, pg, max_width=320, mode="preview")
            if (settings.preview_dir() / "pages" / f"{key}.jpg").is_file():
                thumb_cache_keys[pg.id] = key

    return {
        "project": aggregate.project,
        "project_id": aggregate.project.id,
        "profile": profile,
        "title_page": title_page,
        "pages": pages,
        "page_status": page_status,
        "thumb_cache_keys": thumb_cache_keys,
        "selected_page": selected,
        "page": selected,
        "page_assignments": selected_assignments,
        "assignments": selected_assignments,
        "photos": photos,
        "photos_by_id": {photo.id: photo for photo in photos},
        "assigned_ids": assigned_ids,
        "usage_counts": usage_counts,
        "unused_photos": unused_photos,
        "available_photos": available_photos,
        "photo_filter": "all" if photo_filter == "all" else "unused",
        "slots": slots,
        "slot_count": slot_count,
        "current_layout_key": current_layout_key,
        "slot_assignment_map": slot_assignment_map,
        "slot_overlays": _slot_overlay_data(selected, profile, slots, slot_assignment_map)
        if selected is not None
        else [],
        "catalogue": load_catalogue(),
        "source_states": source_states,
        "error": error,
        "notice": notice,
        "save_state": f"Saved {aggregate.project.updated_at[:19].replace('T', ' ')}",
    }


def _page_context(
    database: WorkspaceDatabase,
    project_id: int,
    page_id: int,
    *,
    settings: GuiSettings | None = None,
) -> dict[str, object] | None:
    """Build the template context for one page fragment."""
    connection = database.connect()
    page = PageRepository(connection).get(page_id)
    if page is None or page.project_id != project_id:
        return None
    assignments = list(AssignmentRepository(connection).list_by_page(page_id))
    photos = PhotoRepository(connection).list(project_id)
    assigned_ids = {assignment.photo_id for assignment in assignments}
    usage_counts = Counter(assignment.photo_id for assignment in assignments)
    unused_photos = [photo for photo in photos if photo.id not in assigned_ids]
    available_photos = [photo for photo in photos if photo.available]
    slots: list = []
    slot_count = 0
    slot_assignment_map: dict = {}
    current_layout_key = ""
    if page.layout_id is not None:
        from photo_composition_designer.project.repositories import LayoutRepository

        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        if layout is not None:
            slots = list(layout.slots)
            slot_count = len(slots)
            current_layout_key = layout.key
            slot_assignment_map = {assignment.slot_id: assignment for assignment in assignments}
    project = ProjectRepository(connection).get(project_id)
    pages = PageRepository(connection).list(project_id)
    profile = profile_from_project(project) if project is not None else OutputProfile.default()
    title_page = profile.calendar.use_title_page and page.page_index == 0

    # Immutable preview asset URL for the sidebar thumbnail. The key is
    # derived from the same render inputs the preview renderer uses.
    thumb_cache_key = ""
    if settings is not None:
        rendering = ProjectRenderingService(
            database,
            anniversaries_path=settings.anniversaries_path,
        )
        thumb_cache_key = preview_cache_key_for(
            rendering, connection, page, max_width=320, mode="preview"
        )
        if not (settings.preview_dir() / "pages" / f"{thumb_cache_key}.jpg").is_file():
            thumb_cache_key = ""

    context = {
        "page": page,
        "project": project,
        "pages": pages,
        "selected_page": page,
        "project_id": project_id,
        "profile": profile,
        "title_page": title_page,
        "assignments": assignments,
        "photos": photos,
        "photos_by_id": {photo.id: photo for photo in photos},
        "unused_photos": unused_photos,
        "available_photos": available_photos,
        "usage_counts": usage_counts,
        "slots": slots,
        "slot_count": slot_count,
        "current_layout_key": current_layout_key,
        "slot_assignment_map": slot_assignment_map,
        "slot_overlays": _slot_overlay_data(page, profile, slots, slot_assignment_map),
        "catalogue": load_catalogue(),
        "thumb_cache_key": thumb_cache_key,
    }
    return context


def _canvas_response(
    request: Request,
    database: WorkspaceDatabase,
    project_id: int,
    page_id: int,
    message: str,
) -> HTMLResponse:
    """Render the editor canvas fragment for one page."""
    context = _page_context(
        database,
        project_id,
        page_id,
        settings=request.app.state.settings,
    )
    if context is None:
        raise HTTPException(404, "page not found")
    context = {**context, "notice": message, "oob_page_thumb": True}
    worker = getattr(request.app.state, "preview_worker", None)
    if worker is not None:
        worker.submit(project_id, page_id, max_width=640, priority=0)
        worker.submit(project_id, page_id, max_width=320, priority=1)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/editor_canvas.html",
        context,
        headers={"HX-Trigger": "pcd:refresh-unused"},
    )
