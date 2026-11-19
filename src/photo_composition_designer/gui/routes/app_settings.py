"""Application-wide settings routes."""

from __future__ import annotations

import os
import shutil
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from photo_composition_designer.core.helpers import get_base_path
from photo_composition_designer.gui.settings import (
    YOLO_MODEL_URL,
    GuiSettings,
    default_yolo_model_path,
    save_app_settings,
)
from photo_composition_designer.gui.templating import TEMPLATES

router = APIRouter()

#: Built-in ini files exposed by the "show built-in format" actions.
BUILT_IN_FILES: dict[str, tuple[str, ...]] = {
    "anniversaries.ini": ("anniversaries.ini",),
    "locations.ini": ("locations_en.ini", "locations_de.ini"),
}

#: Download timeout for the YOLO model asset, in seconds.
DOWNLOAD_TIMEOUT_SECONDS = 60

_TRUTHY = {"1", "true", "on", "yes"}


def _is_checked(value: str) -> bool:
    """Return whether a submitted checkbox value is enabled."""
    return value.strip().lower() in _TRUTHY


def _settings_page(
    request: Request,
    settings: GuiSettings,
    *,
    error: str = "",
    notice: str = "",
    anniversaries_input: str | None = None,
    locations_input: str | None = None,
    yolo_model_path_input: str | None = None,
    object_detection_enabled_input: bool | None = None,
) -> HTMLResponse:
    model_path = (
        yolo_model_path_input
        if yolo_model_path_input is not None
        else (str(settings.yolo_model_path) if settings.yolo_model_path else "")
    )
    enabled = (
        object_detection_enabled_input
        if object_detection_enabled_input is not None
        else settings.object_detection_enabled
    )
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
            "object_detection_enabled": enabled,
            "yolo_model_path": model_path,
            "yolo_model_exists": bool(model_path) and Path(model_path).is_file(),
            "error": error,
            "notice": notice,
        },
    )


def _redirect_to_settings(*, notice: str = "", error: str = "") -> RedirectResponse:
    """Build a redirect back to the settings page with a status message."""
    if error:
        query = f"?error={quote(error)}"
    elif notice:
        query = f"?notice={quote(notice)}"
    else:
        query = ""
    return RedirectResponse(f"/settings{query}", status_code=303)


def _download_yolo_model(destination: Path) -> None:
    """Download the YOLO ONNX model to ``destination`` atomically."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    try:
        with (
            urllib.request.urlopen(YOLO_MODEL_URL, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response,
            temporary.open("wb") as handle,
        ):
            shutil.copyfileobj(response, handle)
        if temporary.stat().st_size == 0:
            raise OSError("downloaded model file is empty")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _run_detector_check(model_path: Path) -> tuple[bool, str]:
    """Load the model and run one inference on a synthetic image.

    Returns:
        A ``(success, message)`` tuple describing the outcome.
    """
    if not model_path.is_file():
        return False, f"Model file not found: {model_path}"

    try:
        from PIL import Image

        from photo_composition_designer.render.object_detector import ObjectDetector

        detector = ObjectDetector(model_path=str(model_path))
        detections = detector.detect(Image.new("RGB", (640, 640), (128, 128, 128)))
    except Exception as exc:  # Report any load/inference failure to the user.
        return False, f"Object detection check failed: {exc}"

    return True, (
        f"Object detection check succeeded ({len(detections)} object(s) found in the test image)."
    )


@router.get("/settings", response_class=HTMLResponse)
def app_settings(
    request: Request,
    saved: bool = False,
    notice: str = "",
    error: str = "",
) -> HTMLResponse:
    """Show settings shared by every project."""
    return _settings_page(
        request,
        request.app.state.settings,
        notice=notice or ("Application settings saved." if saved else ""),
        error=error,
    )


@router.post("/settings", response_model=None)
def update_app_settings(
    request: Request,
    anniversaries_path: Annotated[str, Form()] = "",
    locations_path: Annotated[str, Form()] = "",
    yolo_model_path: Annotated[str, Form()] = "",
    object_detection_enabled: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    """Save the shared file paths and object-detection preferences."""
    settings: GuiSettings = request.app.state.settings
    enabled = _is_checked(object_detection_enabled)
    try:
        anniversaries, locations, model = save_app_settings(
            anniversaries_path=anniversaries_path,
            locations_path=locations_path,
            object_detection_enabled=enabled,
            yolo_model_path=yolo_model_path,
        )
    except (OSError, ValueError) as error:
        return _settings_page(
            request,
            settings,
            error=str(error),
            anniversaries_input=anniversaries_path,
            locations_input=locations_path,
            yolo_model_path_input=yolo_model_path,
            object_detection_enabled_input=enabled,
        )
    request.app.state.settings = replace(
        settings,
        anniversaries_path=anniversaries,
        locations_path=locations,
        object_detection_enabled=enabled,
        yolo_model_path=model,
    )
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/yolo/download", response_model=None)
def download_yolo_model(request: Request) -> RedirectResponse:
    """Download the YOLO model to the OS-specific default location."""
    settings: GuiSettings = request.app.state.settings
    destination = default_yolo_model_path()
    try:
        _download_yolo_model(destination)
    except Exception as exc:  # Network and filesystem failures are user-facing.
        return _redirect_to_settings(error=f"Model download failed: {exc}")

    resolved = destination.resolve()
    request.app.state.settings = replace(settings, yolo_model_path=resolved)
    try:
        save_app_settings(
            anniversaries_path=str(settings.anniversaries_path or ""),
            locations_path=str(settings.locations_path or ""),
            object_detection_enabled=settings.object_detection_enabled,
            yolo_model_path=str(resolved),
        )
    except (OSError, ValueError):
        # The file is on disk; a persistence failure must not hide that.
        pass
    return _redirect_to_settings(notice=f"YOLO model downloaded to {resolved}.")


@router.post("/settings/yolo/test", response_model=None)
def test_yolo_model(request: Request) -> RedirectResponse:
    """Load the configured model and report whether inference works."""
    settings: GuiSettings = request.app.state.settings
    model_path = settings.yolo_model_path or default_yolo_model_path()
    success, message = _run_detector_check(model_path)
    if success:
        return _redirect_to_settings(notice=message)
    return _redirect_to_settings(error=message)


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
