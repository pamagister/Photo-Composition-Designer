"""FastAPI application factory for the local calendar editor.

The application is local-first: it serves the browser UI and a small JSON API
from the same process. All persistence goes through the central SQLite
workspace and application services.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from photo_composition_designer.db.schema import WorkspaceDatabase, read_version
from photo_composition_designer.gui.dependencies import DatabaseDependency
from photo_composition_designer.gui.routes import editor, media, projects
from photo_composition_designer.gui.settings import GuiSettings, load_gui_settings
from photo_composition_designer.gui.templating import BASE_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the workspace schema and close the startup connection."""
    app.state.database.connect()
    yield
    app.state.database.close()


def create_app(settings: GuiSettings | None = None) -> FastAPI:
    """Build the local FastAPI application.

    Args:
        settings: Optional web settings. Defaults are resolved from the
            platform-specific application directories.
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
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(projects.router)
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

    @app.get("/", response_class=HTMLResponse)
    def index() -> RedirectResponse:
        """Send the browser to the project workspace."""
        return RedirectResponse("/projects", status_code=307)

    return app


__all__ = ["BASE_DIR", "create_app"]
