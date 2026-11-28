"""Preview, page-layout and preview-asset routes for a project."""

from __future__ import annotations

import re

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)

from photo_composition_designer.core.errors import ProjectError, ProjectNotFoundError
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    ObjectDetectorDependency,
    ProjectServiceDependency,
    SettingsDependency,
)
from photo_composition_designer.gui.preview_cache import (
    PREVIEW_ASSET_LEASES,
    PREVIEW_ASSET_MAX_AGE_SECONDS,
    PreviewAssetFileResponse,
)
from photo_composition_designer.gui.routes.project_context import (
    _canvas_response,
    _error_redirect,
    _load_project,
    _page_context,
)
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.rendering import ProjectRenderingService
from photo_composition_designer.project.repositories import PageRepository

router = APIRouter()


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
    max_width: int = Query(800, ge=120, le=1600),
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
    max_width: int = Query(800, ge=120, le=1600),
) -> JSONResponse:
    """Return the status of the preview render for a page.

    Returns JSON ``{"status": "ready"|"refreshing"|"error", "revision": N}``.
    If the preview file exists, the status is ``ready``. Otherwise a
    background job is enqueued and the status is ``refreshing``. If the
    worker recorded an error for this exact job, the status is ``error``.
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
        error = getattr(worker, "error_for", None)
        job_error = (
            error(project_id, page_id, max_width=max_width)
            if callable(error)
            else worker.last_error
        )
        if job_error is not None:
            return JSONResponse({"status": "error", "revision": revision, "error": job_error})
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
    bytes, the response is immutable for its 30-day cache lifetime: a new
    revision produces a new key and therefore a new URL.

    Superseded files are retained for 30 days. A response lease prevents the
    cleanup worker from removing a file while it is being transferred.
    """
    if not _PREVIEW_KEY_RE.match(cache_key):
        raise HTTPException(400, "invalid preview cache key")
    path = settings.preview_dir() / "pages" / f"{cache_key}.jpg"
    if not PREVIEW_ASSET_LEASES.acquire(path):
        raise HTTPException(404, "preview not found")
    try:
        return PreviewAssetFileResponse(
            path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": (f"public, max-age={PREVIEW_ASSET_MAX_AGE_SECONDS}, immutable")
            },
        )
    except Exception:
        PREVIEW_ASSET_LEASES.release(path)
        raise


@router.get("/projects/{project_id}/preview", response_model=None)
def preview_project(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
    detector: ObjectDetectorDependency,
    page: int | None = Query(None, description="Page whose large preview to refresh."),
) -> RedirectResponse:
    """Enqueue cached previews and open the selected page.

    Jobs are submitted to the background worker so the request returns
    promptly. The selected page's large preview (800 px) gets high priority;
    the other pages' thumbnails (200 px) get background priority. The
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
            worker.submit(project_id, candidate.id, max_width=200, priority=1)
        # The selected page's large preview is high priority so the visible
        # page catches up before the background thumbnails.
        worker.submit(project_id, target.id, max_width=800, priority=0)
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
    detector: ObjectDetectorDependency,
    layout_key: str = Query(...),
) -> HTMLResponse:
    """Preview a layout change without mutating the project."""
    editing = PageEditingService(database, object_detector=detector)
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
    detector: ObjectDetectorDependency,
    layout_key: str = Form(...),
    confirm: str = Form(""),
) -> HTMLResponse:
    """Apply a layout change, asking for confirmation when photos are displaced."""
    editing = PageEditingService(database, object_detector=detector)
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


__all__ = ["router"]
