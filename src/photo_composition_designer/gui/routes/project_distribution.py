"""Project distribution routes: proposal preview, apply and distribution page."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    ObjectDetectorDependency,
    ProjectServiceDependency,
    SettingsDependency,
)
from photo_composition_designer.gui.routes.project_context import _load_project
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.project.repositories import (
    PageRepository,
    PhotoRepository,
)

router = APIRouter()

#: Best-mode range presets offered by the UI.
_BEST_RANGES = ("2-5", "3-5", "3-6", "3-7")


def _distribution_context(
    database: WorkspaceDatabase,
    project_id: int,
    *,
    mode: str,
    strategy: str,
    seed: int | None,
    best_range: str,
    notice: str = "",
    error: str = "",
) -> dict[str, object]:
    """Build the distribution panel context without mutating project state."""
    from photo_composition_designer.project.distribution import DistributionService

    distribution = DistributionService(database)
    proposal = None
    summary = None
    digest = ""
    page_rows: list[dict[str, object]] = []
    try:
        proposal = distribution.propose(
            project_id,
            mode=mode,
            strategy=strategy,
            seed=seed,
            best_range=best_range,
        )
        connection = database.connect()
        pages = PageRepository(connection).list(project_id)
        photos_by_id = {photo.id: photo for photo in PhotoRepository(connection).list(project_id)}
        capacities = [
            distribution.capacity_for_page(connection, project_id, page) for page in pages
        ]
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
                    "is_auto": page.layout_id is not None
                    and distribution._page_layout_key(connection, page) == "auto",
                }
            )
    except (ValueError, ProjectError) as exc:
        error = error or str(exc)

    return {
        "project_id": project_id,
        "mode": mode,
        "strategy": strategy,
        "seed": seed,
        "best_range": best_range,
        "best_ranges": _BEST_RANGES,
        "proposal": proposal,
        "summary": summary,
        "proposal_digest": digest,
        "page_rows": page_rows,
        "distribution_notice": notice,
        "distribution_error": error,
    }


@router.get("/projects/{project_id}/distribute", response_class=HTMLResponse)
def distribution_page(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
) -> HTMLResponse:
    """Show the distribution workspace for one project.

    The page defaults to the primary use case: distribute all photos across
    automatic pages using the date-aware strategy.
    """
    project = _load_project(service, project_id).project
    context = _distribution_context(
        database,
        project_id,
        mode="all",
        strategy="date_grouped",
        seed=None,
        best_range="3-5",
    )
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


@router.get("/projects/{project_id}/distribute/preview", response_class=HTMLResponse)
def preview_distribution(
    request: Request,
    project_id: int,
    database: DatabaseDependency,
    mode: str = "slots",
    strategy: str = "equal",
    seed: str = "",
    best_range: str = "3-5",
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
    if best_range not in _BEST_RANGES:
        best_range = "3-5"
    context = _distribution_context(
        database,
        project_id,
        mode=mode,
        strategy=strategy,
        seed=effective_seed,
        best_range=best_range,
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
    mode: Annotated[str, Form()] = "slots",
    strategy: Annotated[str, Form()] = "equal",
    seed: Annotated[str, Form()] = "",
    best_range: Annotated[str, Form()] = "3-5",
    proposal_digest: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Apply a previewed distribution proposal in one transaction.

    A supplied digest must match the freshly computed proposal. This rejects
    stale previews and makes a repeated confirmation a no-op.

    Preview jobs for all pages are enqueued to the background worker so the
    request returns promptly; the worker coalesces duplicates and renders
    off the request thread.
    """
    from photo_composition_designer.project.distribution import DistributionService

    distribution = DistributionService(database)
    try:
        effective_seed = int(seed) if seed.strip() else None
    except ValueError:
        effective_seed = None
    if best_range not in _BEST_RANGES:
        best_range = "3-5"

    def response(notice: str = "", error: str = "") -> HTMLResponse | RedirectResponse:
        if request.headers.get("HX-Request") == "true":
            context = _distribution_context(
                database,
                project_id,
                mode=mode,
                strategy=strategy,
                seed=effective_seed,
                best_range=best_range,
                notice=notice,
                error=error,
            )
            return TEMPLATES.TemplateResponse(request, "partials/distribution_area.html", context)
        query = f"?error={quote(error)}" if error else "?distributed=1"
        return RedirectResponse(f"/projects/{project_id}{query}", status_code=303)

    try:
        proposal = distribution.propose(
            project_id,
            mode=mode,
            strategy=strategy,
            seed=effective_seed,
            best_range=best_range,
            object_detector=detector,
        )
    except (ValueError, ProjectError) as exc:
        return response(error=str(exc))

    if not any(proposal.pages) and not proposal.unassigned and not proposal.not_selected:
        return response(notice="All available photos are already distributed.")
    if proposal_digest and proposal_digest != distribution.digest(proposal):
        return response(
            error="This preview is out of date. Review the refreshed proposal before applying."
        )

    try:
        distribution.apply(project_id, proposal, object_detector=detector)
    except (ValueError, ProjectError) as exc:
        return response(error=str(exc))
    # Enqueue background preview jobs for all pages. The request returns
    # promptly; the worker renders off the request thread.
    worker = getattr(request.app.state, "preview_worker", None)
    if worker is not None:
        for page in PageRepository(database.connect()).list(project_id):
            worker.submit(project_id, page.id, max_width=200, priority=1)
    return response(notice="Distribution applied.")


__all__ = ["router"]
