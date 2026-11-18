"""Controlled media endpoints for source photos and cached thumbnails."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.dependencies import DatabaseDependency, SettingsDependency
from photo_composition_designer.io.media import media_type, resolve_source_path
from photo_composition_designer.io.previews import create_thumbnail, thumbnail_path
from photo_composition_designer.project.models import PhotoAsset
from photo_composition_designer.project.repositories import (
    PhotoRepository,
    SourceRootRepository,
)

router = APIRouter()


def _photo(database: WorkspaceDatabase, photo_id: int) -> PhotoAsset:
    """Load a photo or raise a 404 response."""
    photo = PhotoRepository(database.connect()).get(photo_id)
    if photo is None:
        raise HTTPException(404, "photo not found")
    return photo


def _source_path(database: WorkspaceDatabase, photo: PhotoAsset) -> Path:
    """Resolve a photo path inside its source root."""
    root = SourceRootRepository(database.connect()).get(photo.source_root_id)
    if root is None:
        raise HTTPException(404, "source root not found")
    try:
        return resolve_source_path(root.path, photo.relative_path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/media/photos/{photo_id}")
def photo_thumbnail(
    photo_id: int,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> FileResponse:
    """Return a cached thumbnail for one inventory photo."""
    photo = _photo(database, photo_id)
    if not photo.available:
        raise HTTPException(404, "photo is unavailable")
    source = _source_path(database, photo)
    if not source.is_file():
        raise HTTPException(404, "photo file not found")

    target = thumbnail_path(settings.thumbnail_dir(), photo.id, mtime=photo.mtime)
    if not target.is_file():
        create_thumbnail(source, target)
    return FileResponse(
        target,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/media/photos/{photo_id}/original")
def photo_original(
    photo_id: int,
    database: DatabaseDependency,
) -> FileResponse:
    """Return the original source photo without modifying it."""
    photo = _photo(database, photo_id)
    if not photo.available:
        raise HTTPException(404, "photo is unavailable")
    source = _source_path(database, photo)
    if not source.is_file():
        raise HTTPException(404, "photo file not found")
    return FileResponse(
        source,
        media_type=media_type(source),
        headers={"Cache-Control": "private, max-age=3600"},
    )
