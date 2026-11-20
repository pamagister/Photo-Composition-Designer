"""FastAPI application factory for the local calendar editor.

The application is local-first: it serves the browser UI and a small JSON API
from the same process. All persistence goes through the central SQLite
workspace and application services.
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from photo_composition_designer.db.schema import WorkspaceDatabase, read_version
from photo_composition_designer.gui.dependencies import DatabaseDependency, resolve_object_detector
from photo_composition_designer.gui.preview_worker import (
    PreviewWorker,
    SynchronousPreviewWorker,
)
from photo_composition_designer.gui.routes import (
    app_settings,
    editor,
    layouts,
    media,
    project_archive,
    project_settings,
    projects,
)
from photo_composition_designer.gui.routes import export as export_routes
from photo_composition_designer.gui.settings import GuiSettings, load_gui_settings
from photo_composition_designer.gui.templating import BASE_DIR
from photo_composition_designer.io.export import ExportProgressTracker
from photo_composition_designer.render.object_detector import ObjectDetector


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the workspace schema and close the startup connection."""
    app.state.database.connect()
    worker = getattr(app.state, "preview_worker", None)
    if worker is not None:
        worker.start()
    yield
    if worker is not None:
        worker.stop()
    app.state.database.close()


def create_app(
    settings: GuiSettings | None = None,
    *,
    sync_preview_worker: bool = False,
) -> FastAPI:
    """Build the local FastAPI application.

    Args:
        settings: Optional web settings. Defaults are resolved from the
            platform-specific application directories.
        sync_preview_worker: If ``True``, use a synchronous preview worker
            that renders inline. Tests use this for deterministic timing;
            production uses the background :class:`PreviewWorker`.
    """
    settings = settings or load_gui_settings()
    settings.ensure_directories()

    app = FastAPI(
        title="Photo Composition Designer",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = WorkspaceDatabase(settings.workspace_path())
    app.state.export_paths = set()
    app.state.export_progress = ExportProgressTracker()
    app.state.object_detector_cache = {}
    app.state.object_detector_lock = threading.Lock()

    def detector_provider() -> ObjectDetector | None:
        """Resolve the detector from the live app settings."""
        return resolve_object_detector(app)

    if sync_preview_worker:
        app.state.preview_worker = SynchronousPreviewWorker(
            app.state.database,
            preview_dir=settings.preview_dir(),
            anniversaries_path=settings.anniversaries_path,
            detector_provider=detector_provider,
        )
    else:
        app.state.preview_worker = PreviewWorker(
            app.state.database,
            preview_dir=settings.preview_dir(),
            anniversaries_path=settings.anniversaries_path,
            detector_provider=detector_provider,
        )
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(project_archive.router)
    app.include_router(projects.router)
    app.include_router(project_settings.router)
    app.include_router(app_settings.router)
    app.include_router(layouts.router)
    app.include_router(export_routes.router)
    app.include_router(media.router)
    app.include_router(editor.router)

    @app.get("/health")
    def health(database: DatabaseDependency) -> dict[str, Any]:
        """Report process and workspace health for local diagnostics."""
        connection = database.connect()
        return {
            "ok": True,
            "service": "photo-composition-designer",
            "schema_version": read_version(connection),
        }

    @app.post("/shutdown")
    async def shutdown(request: Request) -> JSONResponse:
        """Ask the local uvicorn server to exit.

        The endpoint is only available when the CLI started uvicorn and stored
        its server instance on the application state. The browser polls
        ``/health`` afterwards and reports when the process is gone.
        """
        server = getattr(request.app.state, "server", None)
        if server is None:
            return JSONResponse(
                {
                    "stopping": False,
                    "message": "The server was not started by the CLI and cannot "
                    "be stopped from the browser.",
                },
                status_code=503,
            )
        server.should_exit = True
        return JSONResponse({"stopping": True})

    @app.get("/", response_class=HTMLResponse)
    def index() -> RedirectResponse:
        """Send the browser to the project workspace."""
        return RedirectResponse("/projects", status_code=307)

    return app


__all__ = ["BASE_DIR", "create_app"]
