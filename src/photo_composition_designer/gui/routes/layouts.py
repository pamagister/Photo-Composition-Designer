"""Global layout catalogue editor."""

from __future__ import annotations

import json
import os
import re
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.gui.dependencies import SettingsDependency
from photo_composition_designer.gui.templating import TEMPLATES
from photo_composition_designer.layouts.loader import (
    AUTO_LAYOUT_KEY,
    LayoutTemplate,
    LayoutValidationError,
    layout_choices,
    load_catalogue,
    validate_layout,
)

router = APIRouter()
_LAYOUT_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _layout_context(
    selected_key: str = "",
    *,
    error: str = "",
    notice: str = "",
    name: str = "",
    slots_json: str = "",
) -> dict[str, Any]:
    catalogue = layout_choices()
    selected = load_catalogue().get(selected_key)
    if selected is not None and not name:
        name = selected.name
    if selected is not None and not slots_json:
        slots_json = json.dumps(
            [
                {
                    "key": slot.key,
                    "x": slot.x,
                    "y": slot.y,
                    "width": slot.width,
                    "height": slot.height,
                    "crop_mode": slot.crop_mode,
                }
                for slot in selected.slots
            ],
            indent=2,
        )
    return {
        "page_title": "Global Layout Editor",
        "save_state": "Saved",
        "catalogue": catalogue,
        "selected_key": selected_key,
        "layout_name": name,
        "slots_json": slots_json,
        "error": error,
        "notice": notice,
    }


@router.get("/layouts", response_class=HTMLResponse)
def layout_editor(request: Request, key: str = "", saved: bool = False) -> HTMLResponse:
    """Show global layout versions and the layout editor."""
    return TEMPLATES.TemplateResponse(
        request,
        "layouts.html",
        _layout_context(key, notice="Layout version saved." if saved else ""),
    )


@router.post("/layouts", response_model=None)
def save_layout(
    request: Request,
    settings: SettingsDependency,
    key: Annotated[str, Form()],
    name: Annotated[str, Form()],
    slots_json: Annotated[str, Form()],
) -> HTMLResponse | RedirectResponse:
    """Validate and save a new global layout version."""
    key = key.strip()
    name = name.strip()
    try:
        if key == AUTO_LAYOUT_KEY:
            raise ValueError("The automatic layout is generated and cannot be edited.")
        if not _LAYOUT_KEY.fullmatch(key):
            raise ValueError(
                "Layout key must use lowercase letters, digits, hyphens or underscores."
            )
        if not name:
            raise ValueError("Layout name must not be empty.")
        raw_slots = json.loads(slots_json)
        if not isinstance(raw_slots, list):
            raise ValueError("Slots must be a JSON list.")
        current = load_catalogue().get(key)
        version = current.version + 1 if current else 1
        layout_data = {
            "key": key,
            "version": version,
            "name": name,
            "slots": raw_slots,
        }
        layout: LayoutTemplate = validate_layout(layout_data)
        destination_dir = settings.data_dir / "layouts"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{key}.yaml"
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(
                yaml.safe_dump(layout.as_dict(), sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    except (OSError, json.JSONDecodeError, LayoutValidationError, TypeError, ValueError) as error:
        return TEMPLATES.TemplateResponse(
            request,
            "layouts.html",
            _layout_context(
                key,
                error=str(error),
                name=name,
                slots_json=slots_json,
            ),
            status_code=400,
        )
    return RedirectResponse(f"/layouts?key={key}&saved=1", status_code=303)


__all__ = ["router"]
