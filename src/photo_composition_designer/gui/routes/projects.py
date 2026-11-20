"""Project selection, creation, source management and inventory routes."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)

from photo_composition_designer.core.errors import ProjectError, ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    InventoryServiceDependency,
    ObjectDetectorDependency,
    ProjectServiceDependency,
    SettingsDependency,
)
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.io.media import resolve_source_path
from photo_composition_designer.layouts.loader import load_catalogue
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.models import (
    LayoutSlot,
    PhotoAsset,
    Project,
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


def _distribution_context(
    database: WorkspaceDatabase,
    project_id: int,
    *,
    strategy: str,
    seed: int | None,
    notice: str = "",
    error: str = "",
) -> dict[str, object]:
    """Build the distribution panel context without mutating project state."""
    from photo_composition_designer.project.distribution import DistributionService
    from photo_composition_designer.project.repositories import LayoutRepository

    distribution = DistributionService(database)
    proposal = None
    summary = None
    digest = ""
    page_rows: list[dict[str, object]] = []
    try:
        proposal = distribution.propose(project_id, strategy=strategy, seed=seed)
        connection = database.connect()
        pages = PageRepository(connection).list(project_id)
        photos_by_id = {photo.id: photo for photo in PhotoRepository(connection).list(project_id)}
        layout_repository = LayoutRepository(connection)
        capacities: list[int] = []
        for page in pages:
            layout = (
                layout_repository.get_by_id(page.layout_id) if page.layout_id is not None else None
            )
            capacities.append(len(layout.slots) if layout is not None else 0)
        summary = distribution.summarize(proposal, capacities=capacities)
        digest = distribution.digest(proposal)
        for page, photo_ids, capacity in zip(pages, proposal.pages, capacities, strict=False):
            photos = [photos_by_id[photo_id] for photo_id in photo_ids if photo_id in photos_by_id]
            page_rows.append(
                {
                    "page": page,
                    "samples": photos[:4],
                    "extra_samples": max(0, len(photos) - 4),
                    "assigned": len(photo_ids),
                    "capacity": capacity,
                    "empty": max(0, capacity - len(photo_ids)),
                }
            )
    except (ValueError, ProjectError) as exc:
        error = error or str(exc)

    return {
        "project_id": project_id,
        "strategy": strategy,
        "seed": seed,
        "proposal": proposal,
        "summary": summary,
        "proposal_digest": digest,
        "page_rows": page_rows,
        "distribution_notice": notice,
        "distribution_error": error,
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


def _inventory_context(database: WorkspaceDatabase, project_id: int) -> dict[str, object]:
    """Build the legacy full-inventory fragment context."""
    connection = database.connect()
    photos = PhotoRepository(connection).list(project_id)
    assignments = AssignmentRepository(connection).list_by_project(project_id)
    return {
        "photos": photos,
        "assigned_ids": {assignment.photo_id for assignment in assignments},
    }


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


def _project_title_image_urls(
    database: WorkspaceDatabase,
    projects: list[Project],
    settings: GuiSettings,
) -> dict[int, str]:
    """Return cached first-page preview URLs for project tiles.

    The list page only shows a compact title image. It never renders a preview
    on demand, so projects without a cached preview fall back to a neutral
    placeholder in the template.
    """
    if not projects:
        return {}
    connection = database.connect()
    rendering = ProjectRenderingService(
        database,
        anniversaries_path=settings.anniversaries_path,
    )
    urls: dict[int, str] = {}
    for project in projects:
        pages = PageRepository(connection).list(project.id)
        if not pages:
            continue
        page = pages[0]
        key = preview_cache_key_for(rendering, connection, page, max_width=320, mode="preview")
        if (settings.preview_dir() / "pages" / f"{key}.jpg").is_file():
            urls[project.id] = f"/projects/{project.id}/preview-assets/{key}.jpg"
    return urls


@router.get("/projects", response_class=HTMLResponse)
def list_projects(
    request: Request,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
    error: str = "",
    deleted: bool = False,
) -> HTMLResponse:
    """List all projects in the central workspace."""
    projects = service.list_projects()
    return TEMPLATES.TemplateResponse(
        request,
        "projects.html",
        {
            "projects": projects,
            "title_image_urls": _project_title_image_urls(database, projects, settings),
            "page_title": "Projects",
            "save_state": "Saved",
            "error": error,
            "notice": "Project deleted." if deleted else "",
        },
    )


@router.get("/projects/new", response_class=HTMLResponse)
def new_project_form(request: Request) -> HTMLResponse:
    """Show the new-project form."""
    from photo_composition_designer.layouts.loader import load_catalogue

    return TEMPLATES.TemplateResponse(
        request,
        "new_project.html",
        {
            "page_title": "New project",
            "save_state": "Unsaved",
            "error": "",
            "form": {},
            "catalogue": load_catalogue(),
        },
    )


@router.post("/projects", response_model=None)
def create_project(
    request: Request,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
    inventory: InventoryServiceDependency,
    name: Annotated[str, Form()],
    page_count: Annotated[int, Form()],
    start_date: Annotated[str, Form()],
    layout_key: Annotated[str, Form()] = "",
    source_path: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Create a project with explicit weekly pages, optional layout and source."""
    form = {
        "name": name,
        "page_count": page_count,
        "start_date": start_date,
        "layout_key": layout_key,
        "source_path": source_path,
    }
    catalogue = load_catalogue()
    if layout_key and layout_key not in catalogue:
        return TEMPLATES.TemplateResponse(
            request,
            "new_project.html",
            {
                "page_title": "New project",
                "save_state": "Unsaved",
                "error": f"unknown layout: {layout_key}",
                "form": form,
                "catalogue": catalogue,
            },
            status_code=400,
        )
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
                "catalogue": catalogue,
            },
            status_code=400,
        )

    if layout_key:
        _assign_layout_to_all_pages(database, project.id, layout_key)

    source_error = ""
    if source_path.strip():
        try:
            root = inventory.add_source_root(project.id, source_path)
            inventory.scan(project.id, source_root_id=root.id)
        except ValueError as exc:
            source_error = str(exc)

    if source_error:
        return RedirectResponse(
            f"/projects/{project.id}?created=1&error={quote(source_error)}",
            status_code=303,
        )
    return RedirectResponse(f"/projects/{project.id}?created=1", status_code=303)


def _assign_layout_to_all_pages(
    database: WorkspaceDatabase,
    project_id: int,
    layout_key: str,
) -> None:
    """Assign a layout template to every page in a project."""
    from photo_composition_designer.layouts.loader import load_catalogue
    from photo_composition_designer.project.repositories import (
        LayoutRepository,
        PageRepository,
    )

    catalogue = load_catalogue()
    template = catalogue.get(layout_key)
    if template is None:
        return

    with database.transaction() as connection:
        layout_repo = LayoutRepository(connection)
        page_repo = PageRepository(connection)
        slots = [
            LayoutSlot(
                id=0,
                layout_id=0,
                slot_key=slot.key,
                position=index,
                x=slot.x,
                y=slot.y,
                width=slot.width,
                height=slot.height,
                z_index=0,
                crop_mode=slot.crop_mode,
            )
            for index, slot in enumerate(template.slots)
        ]
        layout = layout_repo.add(template.key, template.version, template.name, slots)
        for page in page_repo.list(project_id):
            page_repo.set_layout(page.id, layout.id, layout.version)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
    detector: ObjectDetectorDependency,
    page: Annotated[int | None, Query(description="Selected page id.")] = None,
    photos: Annotated[str, Query(description="Photo inventory filter.")] = "unused",
    error: str = "",
) -> HTMLResponse:
    """Show one project with its pages, source roots and photo inventory."""
    aggregate = _load_project(service, project_id)
    notice = ""
    if request.query_params.get("created") == "1":
        notice = "Project created. Review the first page, then distribute photos."
    elif request.query_params.get("added") == "1":
        notice = "Source directory added."
    elif request.query_params.get("saved") == "1":
        notice = "Project name saved."
    elif request.query_params.get("settings") == "1":
        notice = "Project settings saved."
    elif request.query_params.get("duplicated") == "1":
        notice = "Project duplicated. Review the copy before editing."
    elif request.query_params.get("previewed") == "1":
        notice = "Page previews refreshed."
    elif request.query_params.get("scanned") == "1":
        notice = "Source directory scanned."
    elif request.query_params.get("remapped") == "1":
        notice = "Source directory relinked and rescanned."
    elif request.query_params.get("activated") == "1":
        notice = "Source directory activated."
    elif request.query_params.get("removed") == "1":
        notice = "Source directory removed."
    elif request.query_params.get("distributed") == "1":
        notice = "Distribution applied."
    context = _project_context(
        database,
        aggregate,
        selected_page_id=page,
        photo_filter=photos,
        error=error,
        notice=notice,
        settings=request.app.state.settings,
    )
    _submit_detection_warmups(
        request,
        aggregate.project.id,
        context.get("available_photos", []),
        aggregate.source_roots,
        detector,
    )
    return TEMPLATES.TemplateResponse(
        request,
        "project.html",
        {"page_title": aggregate.project.name, **context},
    )


@router.get("/projects/{project_id}/distribute", response_class=HTMLResponse)
def distribution_page(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
) -> HTMLResponse:
    """Show the distribution workspace for one project."""
    project = _load_project(service, project_id).project
    context = _distribution_context(database, project_id, strategy="equal", seed=None)
    return TEMPLATES.TemplateResponse(
        request,
        "distribute.html",
        {
            "page_title": f"Distribute - {project.name}",
            "project": project,
            "save_state": "Saved",
            **context,
        },
    )


@router.get("/projects/{project_id}/check", response_class=HTMLResponse)
def check_page(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
) -> HTMLResponse:
    """Show the project check page."""
    project = _load_project(service, project_id).project
    return TEMPLATES.TemplateResponse(
        request,
        "check.html",
        {
            "page_title": f"Check - {project.name}",
            "project": project,
            "save_state": "Saved",
        },
    )


@router.get("/projects/{project_id}/pages/{page_id}", response_class=HTMLResponse)
def project_page_fragment(
    request: Request,
    project_id: int,
    page_id: int,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> HTMLResponse:
    """Return one page fragment for HTMX page navigation."""
    context = _page_context(database, project_id, page_id, settings=settings)
    if context is None:
        raise HTTPException(404, "page not found")
    return TEMPLATES.TemplateResponse(request, "partials/editor_canvas.html", context)


@router.get("/projects/{project_id}/pages/{page_id}/preview")
def page_preview(
    request: Request,
    project_id: int,
    page_id: int,
    database: DatabaseDependency,
    settings: SettingsDependency,
    detector: ObjectDetectorDependency,
    max_width: Annotated[int, Query(ge=120, le=1600)] = 640,
) -> Response:
    """Return a cached reduced-resolution render of one page.

    This route never renders on a cache miss (D3). If the preview file
    exists for the current revision, it is served with ``Cache-Control:
    no-cache`` so the browser always revalidates. If the file is absent,
    a background job is enqueued and ``202 Accepted`` is returned with a
    1x1 transparent placeholder; the client polls the status endpoint
    and reloads the image when it is ready.

    The immutable asset route below (``/preview-assets/{key}.jpg``) is an
    additive optimisation for clients that can address the preview by its
    content-derived cache key.
    """
    del detector  # The worker uses the detector configured at startup.
    rendering = ProjectRenderingService(
        database,
        preview_dir=settings.preview_dir(),
        anniversaries_path=settings.anniversaries_path,
    )
    try:
        path = rendering.preview_cache_path(project_id, page_id, max_width=max_width)
    except ProjectNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if path.is_file():
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"},
        )
    # Cache miss: enqueue a high-priority render and return a placeholder.
    worker = getattr(request.app.state, "preview_worker", None)
    if worker is not None:
        worker.submit(project_id, page_id, max_width=max_width, priority=0)
        # The synchronous worker renders inline; re-check before returning.
        if path.is_file():
            return FileResponse(
                path,
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"},
            )
    # Return a 1x1 transparent GIF as a placeholder. The client polls the
    # status endpoint and reloads the image when it is ready.
    return Response(
        content=_PLACEHOLDER_PNG,
        media_type="image/png",
        status_code=202,
        headers={"Cache-Control": "no-cache"},
    )


#: A 1x1 transparent PNG used as a placeholder while a preview renders.
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6360000000020001e221bc330000000049454e44ae"
    "426082"
)


@router.get("/projects/{project_id}/pages/{page_id}/preview-status")
def preview_status(
    request: Request,
    project_id: int,
    page_id: int,
    database: DatabaseDependency,
    settings: SettingsDependency,
    max_width: Annotated[int, Query(ge=120, le=1600)] = 640,
) -> JSONResponse:
    """Return the status of the preview render for a page.

    Returns JSON ``{"status": "ready"|"refreshing"|"error", "revision": N}``.
    If the preview file exists, the status is ``ready``. Otherwise a
    background job is enqueued and the status is ``refreshing``. If the
    worker recorded an error, the status is ``error``.
    """
    rendering = ProjectRenderingService(
        database,
        preview_dir=settings.preview_dir(),
        anniversaries_path=settings.anniversaries_path,
    )
    connection = database.connect()
    try:
        page = PageRepository(connection).get(page_id)
        if page is None or page.project_id != project_id:
            return JSONResponse(
                {"status": "error", "revision": 0, "error": "page not found"},
                status_code=404,
            )
        revision = page.render_revision
        path = rendering.preview_cache_path(project_id, page_id, max_width=max_width)
    except ProjectNotFoundError as exc:
        return JSONResponse(
            {"status": "error", "revision": 0, "error": str(exc)},
            status_code=404,
        )
    finally:
        connection.close()

    if path.is_file():
        return JSONResponse({"status": "ready", "revision": revision})

    worker = getattr(request.app.state, "preview_worker", None)
    if worker is not None:
        worker.submit(project_id, page_id, max_width=max_width, priority=0)
        if worker.last_error is not None:
            return JSONResponse(
                {"status": "error", "revision": revision, "error": worker.last_error}
            )
    return JSONResponse({"status": "refreshing", "revision": revision})


#: A preview cache key is a 24-character lowercase hex digest (SHA-256
#: truncated). Validating the format prevents path traversal through the
#: asset route's path parameter.
_PREVIEW_KEY_RE = re.compile(r"^[0-9a-f]{24}$")


@router.get("/projects/{project_id}/preview-assets/{cache_key}.jpg")
def preview_asset(
    project_id: int,
    cache_key: str,
    settings: SettingsDependency,
) -> FileResponse:
    """Serve a cached preview by its immutable content-derived cache key.

    The cache key uniquely identifies one rendered preview (revision, layout,
    profile, anniversaries, mode, width). The route never consults mutable
    page state and never renders on a miss; it only serves a file that
    already exists on disk. Because the URL identifies the exact cached
    bytes, the response can be cached forever: a new revision produces a new
    key and therefore a new URL.

    Old revisions' files are retained on disk so an in-flight request for an
    old URL still serves the original complete bytes.
    """
    if not _PREVIEW_KEY_RE.match(cache_key):
        raise HTTPException(400, "invalid preview cache key")
    path = settings.preview_dir() / "pages" / f"{cache_key}.jpg"
    if not path.is_file():
        raise HTTPException(404, "preview not found")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/projects/{project_id}/preview", response_model=None)
def preview_project(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
    detector: ObjectDetectorDependency,
    page: Annotated[int | None, Query(description="Page whose large preview to refresh.")] = None,
) -> RedirectResponse:
    """Enqueue cached previews and open the selected page.

    Jobs are submitted to the background worker so the request returns
    promptly. The selected page's large preview (640 px) gets high priority;
    the other pages' thumbnails (320 px) get background priority. The
    worker coalesces duplicates and renders off the request thread.
    """
    del detector  # The worker uses the detector configured at startup.
    aggregate = _load_project(service, project_id)
    if not aggregate.pages:
        return _error_redirect(project_id, "this project has no pages to preview")
    worker = getattr(request.app.state, "preview_worker", None)
    pages_by_id = {candidate.id: candidate for candidate in aggregate.pages}
    selected = pages_by_id.get(page) if page is not None else None
    target = selected or aggregate.pages[0]
    if worker is not None:
        for candidate in aggregate.pages:
            worker.submit(project_id, candidate.id, max_width=320, priority=1)
        # The selected page's large preview is high priority so the visible
        # page catches up before the background thumbnails.
        worker.submit(project_id, target.id, max_width=640, priority=0)
    return RedirectResponse(
        f"/projects/{project_id}?page={target.id}&previewed=1",
        status_code=303,
    )


def _layout_preview_response(
    request: Request,
    context: dict[str, object],
    *,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the layout preview into the preview panel rather than the canvas."""
    return TEMPLATES.TemplateResponse(
        request,
        "partials/layout_change_preview.html",
        context,
        status_code=status_code,
        headers={"HX-Retarget": "#layout-change-preview", "HX-Reswap": "innerHTML"},
    )


@router.get("/projects/{project_id}/pages/{page_id}/layout/preview", response_class=HTMLResponse)
def preview_layout_change(
    request: Request,
    project_id: int,
    page_id: int,
    database: DatabaseDependency,
    layout_key: Annotated[str, Query()],
) -> HTMLResponse:
    """Preview a layout change without mutating the project."""
    editing = PageEditingService(database)
    try:
        plan = editing.plan_layout_change(project_id, page_id, layout_key)
    except ProjectError as exc:
        return _layout_preview_response(
            request,
            {"project_id": project_id, "page_id": page_id, "error": str(exc)},
            status_code=400,
        )
    return _layout_preview_response(
        request,
        {"project_id": project_id, "page_id": page_id, "plan": plan},
    )


@router.post("/projects/{project_id}/pages/{page_id}/layout", response_model=None)
def apply_layout_change(
    request: Request,
    project_id: int,
    page_id: int,
    database: DatabaseDependency,
    layout_key: Annotated[str, Form()],
    confirm: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Apply a layout change, asking for confirmation when photos are displaced."""
    editing = PageEditingService(database)
    try:
        plan = editing.plan_layout_change(project_id, page_id, layout_key)
        if plan.has_displaced and confirm != "1":
            return _layout_preview_response(
                request,
                {"project_id": project_id, "page_id": page_id, "plan": plan},
            )
        editing.change_layout(project_id, page_id, layout_key)
    except ProjectError as exc:
        return _layout_preview_response(
            request,
            {"project_id": project_id, "page_id": page_id, "error": str(exc)},
            status_code=400,
        )
    return _canvas_response(request, database, project_id, page_id, "Layout changed.")


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
    inventory: InventoryServiceDependency,
    new_root: Annotated[str, Form()],
) -> RedirectResponse:
    """Relink a source root to a new directory and rescan atomically."""
    try:
        inventory.apply_remap(project_id, source_root_id=source_root_id, new_root=new_root)
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
    inventory: InventoryServiceDependency,
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


@router.post("/projects/{project_id}/delete", response_model=None)
def delete_project(
    project_id: int,
    service: ProjectServiceDependency,
) -> RedirectResponse:
    """Delete a project and return to the project list."""
    try:
        service.delete_project(project_id)
    except ProjectError as exc:
        return RedirectResponse(f"/projects?error={quote(str(exc))}", status_code=303)
    return RedirectResponse("/projects?deleted=1", status_code=303)


@router.get("/projects/{project_id}/distribute/preview", response_class=HTMLResponse)
def preview_distribution(
    request: Request,
    project_id: int,
    database: DatabaseDependency,
    strategy: str = "equal",
    seed: str = "",
) -> HTMLResponse:
    """Preview a distribution proposal without mutating project state.

    The seed arrives as an empty string when the optional field is left blank;
    that is a normal request and must preview an unseeded proposal instead of
    failing query validation.
    """
    effective_seed: int | None = None
    error = ""
    raw_seed = seed.strip()
    if raw_seed:
        try:
            effective_seed = int(raw_seed)
        except ValueError:
            error = "Random seed must be a whole number."
    context = _distribution_context(
        database,
        project_id,
        strategy=strategy,
        seed=effective_seed,
        error=error,
    )
    return TEMPLATES.TemplateResponse(request, "partials/distribution_area.html", context)


@router.post("/projects/{project_id}/distribute/apply", response_model=None)
def apply_distribution(
    request: Request,
    project_id: int,
    database: DatabaseDependency,
    settings: SettingsDependency,
    detector: ObjectDetectorDependency,
    strategy: Annotated[str, Form()] = "equal",
    seed: Annotated[str, Form()] = "",
    proposal_digest: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Apply a previewed distribution proposal in one transaction.

    A supplied digest must match the freshly computed proposal. This rejects
    stale previews and makes a repeated confirmation a no-op.

    Preview jobs for all pages are enqueued to the background worker so the
    request returns promptly; the worker coalesces duplicates and renders
    off the request thread.
    """
    del detector  # The worker uses the detector configured at startup.
    from photo_composition_designer.project.distribution import DistributionService

    distribution = DistributionService(database)
    try:
        effective_seed = int(seed) if seed.strip() else None
    except ValueError:
        effective_seed = None

    def response(notice: str = "", error: str = "") -> HTMLResponse | RedirectResponse:
        if request.headers.get("HX-Request") == "true":
            context = _distribution_context(
                database,
                project_id,
                strategy=strategy,
                seed=effective_seed,
                notice=notice,
                error=error,
            )
            return TEMPLATES.TemplateResponse(request, "partials/distribution_area.html", context)
        query = f"?error={quote(error)}" if error else "?distributed=1"
        return RedirectResponse(f"/projects/{project_id}{query}", status_code=303)

    try:
        proposal = distribution.propose(project_id, strategy=strategy, seed=effective_seed)
    except (ValueError, ProjectError) as exc:
        return response(error=str(exc))

    if not any(proposal.pages) and not proposal.unassigned:
        return response(notice="All available photos are already distributed.")
    if proposal_digest and proposal_digest != distribution.digest(proposal):
        return response(
            error="This preview is out of date. Review the refreshed proposal before applying."
        )

    try:
        distribution.apply(project_id, proposal)
    except (ValueError, ProjectError) as exc:
        return response(error=str(exc))
    # Enqueue background preview jobs for all pages. The request returns
    # promptly; the worker renders off the request thread.
    worker = getattr(request.app.state, "preview_worker", None)
    if worker is not None:
        for page in PageRepository(database.connect()).list(project_id):
            worker.submit(project_id, page.id, max_width=320, priority=1)
    return response(notice="Distribution applied.")


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
