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
