"""Application-wide settings routes."""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.gui.settings import GuiSettings, save_anniversaries_path
from photo_composition_designer.gui.templating import TEMPLATES

router = APIRouter()


def _settings_page(
    request: Request,
    settings: GuiSettings,
    *,
    error: str = "",
    notice: str = "",
    path_input: str | None = None,
) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request,
        "app_settings.html",
        {
            "page_title": "Application Settings",
            "save_state": "Saved",
            "anniversaries_path": (
                path_input
                if path_input is not None
                else str(settings.anniversaries_path)
                if settings.anniversaries_path
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
) -> HTMLResponse | RedirectResponse:
    """Save the shared anniversary configuration path."""
    settings: GuiSettings = request.app.state.settings
    try:
        path = save_anniversaries_path(anniversaries_path)
    except (OSError, ValueError) as error:
        return _settings_page(
            request,
            settings,
            error=str(error),
            path_input=anniversaries_path,
        )
    request.app.state.settings = replace(settings, anniversaries_path=path)
    return RedirectResponse("/settings?saved=1", status_code=303)


__all__ = ["router"]
