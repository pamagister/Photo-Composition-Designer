"""Shared FastAPI dependencies for the local web application."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

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


def get_object_detector(request: Request) -> ObjectDetector | None:
    """Return a cached object detector for the active app settings.

    The detector is expensive to construct because it loads the ONNX model, so
    instances are cached on the application state keyed by model path and
    modification time. Returning ``None`` means object-aware cropping is
    disabled or the model is unavailable, and callers fall back to plain
    geometric cropping.
    """
    settings: GuiSettings = request.app.state.settings
    if not settings.object_detection_enabled or settings.yolo_model_path is None:
        return None

    path = settings.yolo_model_path
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None

    cache = getattr(request.app.state, "object_detector_cache", None)
    if cache is None:
        cache = {}
        request.app.state.object_detector_cache = cache

    key = (str(path), mtime)
    if key not in cache:
        cache[key] = build_object_detector(enabled=True, model_path=path)
    return cache[key]


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
