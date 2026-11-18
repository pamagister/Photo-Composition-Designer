"""Browser export routes for rendered project pages and PDF output."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from photo_composition_designer.core.errors import ProjectError, ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    ProjectServiceDependency,
    SettingsDependency,
)
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.io.export import ExportResult, ProjectExporter
from photo_composition_designer.project.rendering import profile_from_project
from photo_composition_designer.project.services import ProjectService

router = APIRouter()


def _export_folder(
    settings: GuiSettings,
    project_id: int,
    folder: str,
) -> tuple[Path, str]:
    """Resolve a relative export folder inside the workspace export directory."""
    relative = Path(folder.strip() or f"project_{project_id}")
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("export folder must be a relative path inside the export directory")
    root = settings.export_dir().resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("export folder must stay inside the export directory")
    return target, relative.as_posix()


def _export_file_url(project_id: int, folder: str, path: Path) -> str:
    """Return a safe download URL for one exported file."""
    return f"/projects/{project_id}/export/files?folder={quote(folder)}&name={quote(path.name)}"


def _export_context(
    settings: GuiSettings,
    project_id: int,
    *,
    folder: str = "",
    result: ExportResult | None = None,
    error: str = "",
) -> dict[str, object]:
    """Build the template context for export pages and fragments."""
    default_folder = folder.strip() or f"project_{project_id}"
    file_rows: list[dict[str, object]] = []
    pdf_url = ""
    if result is not None:
        file_rows = [
            {
                "name": path.name,
                "size": path.stat().st_size if path.is_file() else 0,
                "url": _export_file_url(project_id, default_folder, path),
            }
            for path in result.rendered
        ]
        if result.pdf_path is not None:
            pdf_url = _export_file_url(project_id, default_folder, result.pdf_path)
    return {
        "project_id": project_id,
        "folder": default_folder,
        "export_root": settings.export_dir(),
        "result": result,
        "file_rows": file_rows,
        "pdf_url": pdf_url,
        "error": error,
    }


def _get_project(service: ProjectService, project_id: int):
    """Return one project or raise a 404 response."""
    try:
        return service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def _export_page(
    request: Request,
    service: ProjectService,
    settings: GuiSettings,
    project_id: int,
    *,
    context: dict[str, object] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the full export page."""
    project = _get_project(service, project_id)
    profile = profile_from_project(project)
    return TEMPLATES.TemplateResponse(
        request,
        "export.html",
        {
            "page_title": f"Export - {project.name}",
            "project": project,
            "profile": profile,
            "save_state": "Saved",
            **(_export_context(settings, project_id) if context is None else context),
        },
        status_code=status_code,
    )


@router.get("/projects/{project_id}/export", response_class=HTMLResponse)
def export_page(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    settings: SettingsDependency,
) -> HTMLResponse:
    """Show the project export form and effective output settings."""
    return _export_page(request, service, settings, project_id)


@router.post("/projects/{project_id}/export", response_model=None)
def run_export(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
    folder: Annotated[str, Form()] = "",
    pdf: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Export project pages and a PDF into the workspace export directory."""
    project = _get_project(service, project_id)
    profile = profile_from_project(project)
    try:
        target, relative_folder = _export_folder(settings, project_id, folder)
        result = ProjectExporter(database).render_project(
            project_id,
            target,
            write_pdf=bool(pdf),
        )
    except (OSError, ValueError, ProjectError) as exc:
        context = _export_context(
            settings,
            project_id,
            folder=folder,
            error=str(exc),
        )
        return _export_response(
            request,
            service,
            settings,
            project_id,
            context,
            profile=profile,
            status_code=400,
        )

    context = _export_context(
        settings,
        project_id,
        folder=relative_folder,
        result=result,
        error="",
    )
    return _export_response(
        request,
        service,
        settings,
        project_id,
        context,
        profile=profile,
    )


def _export_response(
    request: Request,
    service: ProjectService,
    settings: GuiSettings,
    project_id: int,
    context: dict[str, object],
    *,
    profile: OutputProfile,
    status_code: int = 200,
) -> HTMLResponse:
    """Return a fragment for HTMX requests or the full export page."""
    if request.headers.get("HX-Request") == "true":
        project = _get_project(service, project_id)
        return TEMPLATES.TemplateResponse(
            request,
            "partials/export_result.html",
            {
                "project": project,
                "profile": profile,
                "save_state": "Saved",
                **context,
            },
            status_code=status_code,
        )
    return _export_page(
        request,
        service,
        settings,
        project_id,
        context={**context},
        status_code=status_code,
    )


@router.get("/projects/{project_id}/export/files")
def export_file(
    project_id: int,
    settings: SettingsDependency,
    folder: str = "",
    name: str = "",
) -> FileResponse:
    """Serve an exported file from inside the workspace export directory."""
    try:
        target, _ = _export_folder(settings, project_id, folder)
    except ValueError as exc:
        raise HTTPException(404, "export file not found") from exc
    filename = Path(name)
    if not name or filename.name != name:
        raise HTTPException(404, "export file not found")
    candidate = (target / filename).resolve()
    if not candidate.is_relative_to(target) or not candidate.is_file():
        raise HTTPException(404, "export file not found")
    media_type = "application/pdf" if candidate.suffix.lower() == ".pdf" else "image/png"
    return FileResponse(
        candidate,
        media_type=media_type,
        filename=candidate.name,
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["router"]
