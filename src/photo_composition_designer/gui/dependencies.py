"""Shared FastAPI dependencies for the local web application."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, Request

from photo_composition_designer.core.locations import Locations
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.services import ProjectService
from photo_composition_designer.render.object_detector import ObjectDetector, build_object_detector


def get_settings(request: Request) -> GuiSettings:
    """Return the settings captured when the application was created."""
    return request.app.state.settings


def get_database(request: Request) -> Iterator[WorkspaceDatabase]:
    """Open one workspace database for the current request and close it after."""
    database = WorkspaceDatabase(request.app.state.settings.workspace_path())
    try:
        yield database
    finally:
        database.close()


SettingsDependency = Annotated[GuiSettings, Depends(get_settings)]
DatabaseDependency = Annotated[WorkspaceDatabase, Depends(get_database)]


def resolve_object_detector(app: FastAPI) -> ObjectDetector | None:
    """Return a cached object detector for the active app settings.

    The detector is expensive to construct because it loads the ONNX model, so
    instances are cached on the application state keyed by model path and
    modification time. Returning ``None`` means object-aware cropping is
    disabled or the model is unavailable, and callers fall back to plain
    geometric cropping.

    The cache is shared with the background preview worker so both paths use
    the same ONNX session instead of loading the model twice.
    """
    settings: GuiSettings = app.state.settings
    if not settings.object_detection_enabled or settings.yolo_model_path is None:
        return None

    path = settings.yolo_model_path
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None

    cache = getattr(app.state, "object_detector_cache", None)
    if cache is None:
        cache = {}
        app.state.object_detector_cache = cache
    lock = getattr(app.state, "object_detector_lock", None)
    if lock is None:
        lock = threading.Lock()
        app.state.object_detector_lock = lock

    key = (str(path), mtime)
    with lock:
        detector = cache.get(key)
        if detector is None:
            detector = build_object_detector(enabled=True, model_path=path)
            cache[key] = detector
        return detector


def get_object_detector(request: Request) -> ObjectDetector | None:
    """Return a cached object detector for the active app settings."""
    return resolve_object_detector(request.app)


ObjectDetectorDependency = Annotated[ObjectDetector | None, Depends(get_object_detector)]


def project_service(database: DatabaseDependency) -> ProjectService:
    """Build a project service for one request."""
    return ProjectService(database)


def inventory_service(
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> InventoryService:
    """Build an inventory service using the configured location overrides."""
    return InventoryService(
        database,
        locations=Locations.with_overrides(settings.locations_path),
    )


ProjectServiceDependency = Annotated[ProjectService, Depends(project_service)]
InventoryServiceDependency = Annotated[InventoryService, Depends(inventory_service)]
