"""Browser export routes for rendered project pages and PDF output."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from photo_composition_designer.core.errors import ProjectError, ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.gui.dependencies import (
    DatabaseDependency,
    ObjectDetectorDependency,
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
    """Resolve a chosen local export folder or a workspace-relative folder."""
    normalized = folder.strip()
    if normalized:
        chosen = Path(normalized).expanduser()
        if chosen.is_absolute():
            target = chosen.resolve()
            if target == Path(target.anchor):
                raise ValueError("export folder cannot be a filesystem root")
            return target, str(target)
        relative = chosen
    else:
        relative = Path(f"project_{project_id}")
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("export folder must be a relative path inside the export directory")
    root = settings.export_dir().resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("export folder must stay inside the export directory")
    return target, relative.as_posix()


def _pictures_directory() -> Path | None:
    """Return the configured OS pictures directory when it exists."""
    home = Path.home()
    candidates: list[Path] = []
    if os.name == "nt":
        candidates.append(Path(os.environ.get("USERPROFILE", home)) / "Pictures")
    elif sys.platform == "darwin":
        candidates.append(home / "Pictures")
    else:
        user_dirs = home / ".config" / "user-dirs.dirs"
        if user_dirs.is_file():
            for line in user_dirs.read_text(encoding="utf-8").splitlines():
                if line.startswith("XDG_PICTURES_DIR="):
                    configured = line.split("=", 1)[1].strip().strip('"')
                    candidates.append(Path(configured.replace("$HOME", str(home))).expanduser())
                    break
        candidates.extend((home / "Pictures", home / "Bilder"))
    return next((candidate for candidate in candidates if candidate.is_dir()), None)


def _default_export_folder(settings: GuiSettings, project_id: int) -> Path:
    """Choose a project-specific directory under Pictures when available."""
    pictures = _pictures_directory()
    if pictures is not None:
        return pictures / "Photo-Composition-Designer" / f"project_{project_id}"
    return settings.export_dir() / f"project_{project_id}"


def _open_in_file_manager(path: Path) -> bool:
    """Open a folder in the platform file manager, returning success."""
    try:
        if sys.platform == "win32":
            start_file = getattr(os, "startfile", None)
            if start_file is None:
                return False
            start_file(path)
        elif sys.platform == "darwin":
            command = ["open", str(path)]
        else:
            command = ["xdg-open", str(path)]
        if sys.platform != "win32":
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError:
        return False
    return True


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
    notice: str = "",
    open_error: str = "",
    profile: OutputProfile | None = None,
    dpi: str = "",
    jpeg_quality: str = "",
) -> dict[str, object]:
    """Build the template context for export pages and fragments."""
    effective_profile = profile or OutputProfile.default()
    default_folder = folder.strip() or str(_default_export_folder(settings, project_id))
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
        "dpi": dpi.strip() or str(effective_profile.size.dpi),
        "jpeg_quality": jpeg_quality.strip() or str(effective_profile.size.jpeg_quality),
        "result": result,
        "file_rows": file_rows,
        "pdf_url": pdf_url,
        "folder_url": f"/projects/{project_id}/export/folder?folder={quote(default_folder)}",
        "error": error,
        "notice": notice,
        "open_error": open_error,
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
    error: str = "",
    notice: str = "",
    open_error: str = "",
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
            **(
                _export_context(
                    settings,
                    project_id,
                    profile=profile,
                    error=error,
                    notice=notice,
                    open_error=open_error,
                )
                if context is None
                else context
            ),
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
    notice = "Export folder opened." if request.query_params.get("opened") == "1" else ""
    open_error = request.query_params.get("open_error", "")
    return _export_page(
        request,
        service,
        settings,
        project_id,
        notice=notice,
        open_error=open_error,
    )


@router.get("/projects/{project_id}/export/folder")
def open_export_folder(
    request: Request,
    project_id: int,
    settings: SettingsDependency,
    folder: str = "",
) -> RedirectResponse:
    """Open a previously exported folder in the OS file manager."""
    try:
        target, _ = _export_folder(settings, project_id, folder)
    except ValueError as exc:
        raise HTTPException(404, "export folder not found") from exc
    if target.resolve() not in request.app.state.export_paths or not target.is_dir():
        raise HTTPException(404, "export folder not found")
    if not _open_in_file_manager(target):
        return RedirectResponse(
            f"/projects/{project_id}/export?open_error="
            f"{quote('Could not open the export folder in the file manager.')}",
            status_code=303,
        )
    return RedirectResponse(f"/projects/{project_id}/export?opened=1", status_code=303)


@router.post("/projects/{project_id}/export", response_model=None)
def run_export(
    request: Request,
    project_id: int,
    service: ProjectServiceDependency,
    database: DatabaseDependency,
    settings: SettingsDependency,
    detector: ObjectDetectorDependency,
    folder: Annotated[str, Form()] = "",
    jpg: Annotated[str, Form()] = "",
    pdf: Annotated[str, Form()] = "",
    dpi: Annotated[str, Form()] = "",
    jpeg_quality: Annotated[str, Form()] = "",
) -> HTMLResponse:
    """Export project pages as JPG files and/or a PDF into the chosen folder."""
    project = _get_project(service, project_id)
    profile = profile_from_project(project)
    requested_dpi = dpi.strip()
    requested_quality = jpeg_quality.strip()
    progress = request.app.state.export_progress
    progress_started = False
    try:
        write_jpg = bool(jpg)
        write_pdf = bool(pdf)
        if not write_jpg and not write_pdf:
            raise ValueError("Select at least one export format: JPG or PDF.")
        effective_dpi = int(requested_dpi) if requested_dpi else profile.size.dpi
        if effective_dpi < 1:
            raise ValueError("DPI must be at least 1")
        if write_jpg:
            effective_quality = (
                int(requested_quality) if requested_quality else profile.size.jpeg_quality
            )
            if not 1 <= effective_quality <= 100:
                raise ValueError("JPEG quality must be between 1 and 100")
        else:
            effective_quality = profile.size.jpeg_quality
        requested_folder = folder.strip() or str(_default_export_folder(settings, project_id))
        target, relative_folder = _export_folder(settings, project_id, requested_folder)
        progress.start(project_id)
        progress_started = True
        result = ProjectExporter(
            database,
            anniversaries_path=settings.anniversaries_path,
            object_detector=detector,
        ).render_project(
            project_id,
            target,
            write_pdf=write_pdf,
            write_pages=write_jpg,
            image_format="JPEG",
            jpeg_quality=effective_quality,
            dpi=effective_dpi,
            progress=lambda completed, total: progress.update(project_id, completed, total),
        )
        request.app.state.export_paths.add(target.resolve())
        progress.finish(project_id, status="done")
    except (OSError, ValueError, ProjectError) as exc:
        if progress_started:
            progress.finish(project_id, status="error", error=str(exc))
        context = _export_context(
            settings,
            project_id,
            folder=folder,
            error=str(exc),
            profile=profile,
            dpi=requested_dpi,
            jpeg_quality=requested_quality,
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
        profile=profile,
        dpi=str(effective_dpi),
        jpeg_quality=str(effective_quality),
    )
    return _export_response(
        request,
        service,
        settings,
        project_id,
        context,
        profile=profile,
    )


@router.get("/projects/{project_id}/export/progress")
def export_progress(request: Request, project_id: int) -> JSONResponse:
    """Return the current export progress for the browser indicator."""
    state = request.app.state.export_progress.get(project_id)
    return JSONResponse(
        {
            "status": state.status,
            "completed": state.completed,
            "total": state.total,
            "percent": state.percent,
            "error": state.error,
        }
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
    request: Request,
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
    if target.resolve() not in request.app.state.export_paths:
        raise HTTPException(404, "export file not found")
    filename = Path(name)
    if not name or filename.name != name:
        raise HTTPException(404, "export file not found")
    candidate = (target / filename).resolve()
    if not candidate.is_relative_to(target) or not candidate.is_file():
        raise HTTPException(404, "export file not found")
    suffix = candidate.suffix.lower()
    if suffix == ".pdf":
        media_type = "application/pdf"
    elif suffix in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    else:
        media_type = "image/png"
    return FileResponse(
        candidate,
        media_type=media_type,
        filename=candidate.name,
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["router"]
