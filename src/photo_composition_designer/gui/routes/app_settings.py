"""Application-wide settings routes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.helpers import get_base_path
from photo_composition_designer.gui.settings import GuiSettings, save_paths
from photo_composition_designer.gui.templating import TEMPLATES

router = APIRouter()

#: Built-in ini files exposed by the "show built-in format" actions.
BUILT_IN_FILES: dict[str, tuple[str, ...]] = {
    "anniversaries.ini": ("anniversaries.ini",),
    "locations.ini": ("locations_en.ini", "locations_de.ini"),
}


def _settings_page(
    request: Request,
    settings: GuiSettings,
    *,
    error: str = "",
    notice: str = "",
    anniversaries_input: str | None = None,
    locations_input: str | None = None,
) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "app_settings.html",
        {
            "page_title": "Application Settings",
            "save_state": "Saved",
            "anniversaries_path": (
                anniversaries_input
                if anniversaries_input is not None
                else str(settings.anniversaries_path)
                if settings.anniversaries_path
                else ""
            ),
            "locations_path": (
                locations_input
                if locations_input is not None
                else str(settings.locations_path)
                if settings.locations_path
                else ""
            ),
            "error": error,
            "notice": notice,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
def app_settings(request: Request, saved: bool = False) -> HTMLResponse:
    """Show settings shared by every project."""
    return _settings_page(
        request,
        request.app.state.settings,
        notice="Application settings saved." if saved else "",
    )


@router.post("/settings", response_model=None)
def update_app_settings(
    request: Request,
    anniversaries_path: Annotated[str, Form()] = "",
    locations_path: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Save the shared anniversary and location configuration paths."""
    settings: GuiSettings = request.app.state.settings
    try:
        anniversaries, locations = save_paths(
            anniversaries_path=anniversaries_path,
            locations_path=locations_path,
        )
    except (OSError, ValueError) as error:
        return _settings_page(
            request,
            settings,
            error=str(error),
            anniversaries_input=anniversaries_path,
            locations_input=locations_path,
        )
    request.app.state.settings = replace(
        settings,
        anniversaries_path=anniversaries,
        locations_path=locations,
    )
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.get("/settings/built-in/{name}", response_class=HTMLResponse)
def show_built_in_settings(request: Request, name: str) -> HTMLResponse:
    """Show the bundled ini file format without requiring a local file."""
    filenames = BUILT_IN_FILES.get(name)
    if filenames is None:
        raise HTTPException(404, "unknown built-in settings file")

    base_path = get_base_path()
    sections = []
    for filename in filenames:
        path: Path = base_path / filename
        text = path.read_text(encoding="utf-8") if path.is_file() else "File not found."
        sections.append({"name": filename, "text": text})
    return TEMPLATES.TemplateResponse(
        request,
        "built_in_settings.html",
        {
            "page_title": f"Built-in {name}",
            "save_state": "Built-in",
            "file_name": name,
            "sections": sections,
        },
    )


__all__ = ["router"]
