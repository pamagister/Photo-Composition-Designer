"""FastAPI route modules for the local web application."""

from photo_composition_designer.gui.routes import (
    media,
    project_distribution,
    project_inventory,
    project_lifecycle,
    project_preview,
)

__all__ = [
    "media",
    "project_distribution",
    "project_inventory",
    "project_lifecycle",
    "project_preview",
]
