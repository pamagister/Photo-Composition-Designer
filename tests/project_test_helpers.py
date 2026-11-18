"""Shared fixtures and builders for project persistence tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from Photo_Composition_Designer.project.db import WorkspaceDatabase
from Photo_Composition_Designer.project.models import (
    LayoutDefinition,
    LayoutSlot,
    PhotoAsset,
    Project,
    SourceRoot,
)
from Photo_Composition_Designer.project.repositories import (
    LayoutRepository,
    PhotoRepository,
    SourceRootRepository,
)
from Photo_Composition_Designer.project.services import ProjectService

FIXED_NOW = "2026-11-18T00:00:00+00:00"


def make_database(tmp_path: Path) -> WorkspaceDatabase:
    """Create a workspace database under a temporary directory."""
    return WorkspaceDatabase(tmp_path / "workspace.sqlite3")


def make_service(database: WorkspaceDatabase) -> ProjectService:
    """Create a project service for a database."""
    return ProjectService(database)


def make_project(
    service: ProjectService,
    *,
    name: str = "Family Calendar",
    page_count: int = 2,
) -> Project:
    """Create a project with deterministic settings for tests."""
    return service.create_project(
        name=name,
        page_count=page_count,
        start_date=datetime(2027, 1, 4),
        settings={"calendar": {"language": "en_US", "useCalendar": True}},
        output_profile={"size": {"width": 216, "height": 154, "dpi": 300}},
        import_metadata={"source": "test"},
    )


def make_layout(
    repository: LayoutRepository,
    *,
    key: str = "grid-2",
    version: int = 1,
    slot_count: int = 2,
) -> LayoutDefinition:
    """Create a simple layout with evenly divided slots."""
    slots = [
        LayoutSlot(
            id=0,
            layout_id=0,
            slot_key=f"slot_{index + 1}",
            position=index,
            x=0.0,
            y=0.0,
            width=1.0,
            height=1.0,
            z_index=index,
            crop_mode="cover",
        )
        for index in range(slot_count)
    ]
    return repository.add(key, version, "Grid", slots)


def add_source_root(
    repository: SourceRootRepository,
    project_id: int,
    path: str = "/photos",
) -> SourceRoot:
    """Add an active source root for a project."""
    return repository.add(
        project_id,
        path,
        active=True,
        source_identity=path,
        created_at=FIXED_NOW,
    )


def make_photo(
    repository: PhotoRepository,
    project_id: int,
    source_root_id: int,
    *,
    relative_path: str = "photo.jpg",
    file_size: int = 123,
) -> PhotoAsset:
    """Insert one photo asset and return the stored row."""
    asset = PhotoAsset(
        id=0,
        project_id=project_id,
        source_root_id=source_root_id,
        relative_path=relative_path,
        filename=Path(relative_path).name,
        file_size=file_size,
        mtime=1.0,
        digest=None,
        width=100,
        height=80,
        captured_at="2027-01-04T12:00:00",
        gps_lat=None,
        gps_lon=None,
        available=True,
        created_at=FIXED_NOW,
    )
    repository.upsert_many([asset])
    stored = repository.list(project_id)
    return next(photo for photo in stored if photo.relative_path == relative_path)
