"""Project lifecycle routes: listing, creation, detail and deletion."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    InventoryServiceDependency,
    ObjectDetectorDependency,
    ProjectServiceDependency,
    SettingsDependency,
)
from photo_composition_designer.gui.routes.project_context import (
    _error_redirect,
    _load_project,
    _project_context,
    _submit_detection_warmups,
)
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.layouts.loader import (
    AUTO_LAYOUT_KEY,
    AUTO_LAYOUT_NAME,
    layout_choices,
    load_catalogue,
)
from photo_composition_designer.project.models import LayoutSlot, Project
from photo_composition_designer.project.rendering import (
    ProjectRenderingService,
    preview_cache_key_for,
)
from photo_composition_designer.project.repositories import PageRepository

router = APIRouter()


def _assign_layout_to_all_pages(
    database: WorkspaceDatabase,
    project_id: int,
    layout_key: str,
) -> None:
    """Assign a layout template to every page in a project."""
    from photo_composition_designer.project.repositories import (
        LayoutRepository,
    )

    if layout_key == AUTO_LAYOUT_KEY:
        # Auto geometry depends on photos, which a fresh project does not have
        # yet, so every page receives its own empty automatic snapshot. Photo
        # management and distribution regenerate it later.
        with database.transaction() as connection:
            layout_repo = LayoutRepository(connection)
            page_repo = PageRepository(connection)
            for page in page_repo.list(project_id):
                version = layout_repo.next_version(AUTO_LAYOUT_KEY)
                layout = layout_repo.add(AUTO_LAYOUT_KEY, version, AUTO_LAYOUT_NAME, [])
                page_repo.set_layout(page.id, layout.id, layout.version)
        return

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
    return TEMPLATES.TemplateResponse(
        request,
        "new_project.html",
        {
            "page_title": "New project",
            "save_state": "Unsaved",
            "error": "",
            "form": {},
            "catalogue": layout_choices(),
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
    catalogue = layout_choices()
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
    elif request.query_params.get("assignments") == "1":
        notice = "Project assignments cleared."
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


__all__ = ["router"]
