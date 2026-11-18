"""Project photo inventory scanning and source-root management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from photo_composition_designer.core.photo import Photo
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.scan import find_image_files
from photo_composition_designer.project.models import PhotoAsset, SourceRoot
from photo_composition_designer.project.repositories import (
    PhotoRepository,
    ProjectRepository,
    SourceRootRepository,
)


def _now() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


def _resolve_directory(path: str | Path) -> Path:
    """Resolve a user-supplied directory without requiring it to exist."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


@dataclass(frozen=True)
class ScanSummary:
    """Outcome of one source-root scan."""

    source_root_id: int
    source_path: str
    discovered: int
    added: int
    updated: int
    unavailable: int
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary."""
        return {
            "source_root_id": self.source_root_id,
            "source_path": self.source_path,
            "discovered": self.discovered,
            "added": self.added,
            "updated": self.updated,
            "unavailable": self.unavailable,
            "warnings": list(self.warnings),
        }


class InventoryService:
    """Manage source roots and the persisted photo inventory for a project."""

    def __init__(self, database: WorkspaceDatabase) -> None:
        self._database = database

    def add_source_root(
        self,
        project_id: int,
        path: str | Path,
        *,
        active: bool = True,
    ) -> SourceRoot:
        """Add a validated source directory to a project.

        Raises:
            ValueError: If the directory does not exist.
        """
        if ProjectRepository(self._database.connect()).get(project_id) is None:
            raise ValueError(f"project {project_id} does not exist")
        resolved = _resolve_directory(path)
        if not resolved.is_dir():
            raise ValueError(f"source directory does not exist: {resolved}")

        with self._database.transaction() as connection:
            repository = SourceRootRepository(connection)
            root = repository.add(
                project_id,
                str(resolved),
                active=False,
                source_identity=str(resolved),
                created_at=_now(),
            )
            if active:
                repository.set_active(project_id, root.id)
            stored = repository.get(root.id)
            if stored is None:
                raise RuntimeError("source root disappeared immediately after insert")
            return stored

    def scan(
        self,
        project_id: int,
        *,
        source_root_id: int | None = None,
    ) -> ScanSummary:
        """Scan one source root and reconcile the persisted photo inventory.

        Existing photos that are no longer present are marked unavailable; their
        rows and assignments are retained.
        """
        with self._database.transaction() as connection:
            if ProjectRepository(connection).get(project_id) is None:
                raise ValueError(f"project {project_id} does not exist")

            root_repository = SourceRootRepository(connection)
            root = (
                root_repository.get(source_root_id)
                if source_root_id is not None
                else root_repository.get_active(project_id)
            )
            if root is None or root.project_id != project_id:
                raise ValueError("no source directory configured for this project")

            root_path = Path(root.path)
            if not root_path.is_dir():
                raise ValueError(f"source directory is missing: {root_path}")

            photo_repository = PhotoRepository(connection)
            existing = {
                photo.relative_path: photo
                for photo in photo_repository.list(project_id)
                if photo.source_root_id == root.id
            }
            warnings: list[str] = []
            assets: list[PhotoAsset] = []
            timestamp = _now()

            for path in find_image_files(root_path):
                relative_path = path.relative_to(root_path).as_posix()
                try:
                    stat = path.stat()
                    with Image.open(path) as image:
                        width, height = image.size
                    photo = Photo(path)
                    captured = photo.get_date()
                    captured_at = (
                        None if captured == datetime.max else captured.isoformat(timespec="seconds")
                    )
                    location = photo.get_location()
                except (OSError, ValueError) as exc:
                    warnings.append(f"{relative_path}: {exc}")
                    continue

                assets.append(
                    PhotoAsset(
                        id=0,
                        project_id=project_id,
                        source_root_id=root.id,
                        relative_path=relative_path,
                        filename=path.name,
                        file_size=int(stat.st_size),
                        mtime=float(stat.st_mtime),
                        digest=None,
                        width=int(width),
                        height=int(height),
                        captured_at=captured_at,
                        gps_lat=location[0] if location else None,
                        gps_lon=location[1] if location else None,
                        available=True,
                        created_at=timestamp,
                    )
                )

            discovered = {asset.relative_path for asset in assets}
            added = sum(1 for asset in assets if asset.relative_path not in existing)
            photo_repository.upsert_many(assets)

            unavailable = 0
            for relative_path, photo in existing.items():
                if relative_path not in discovered:
                    photo_repository.set_availability(photo.id, False)
                    unavailable += 1

            root_repository.update_scan(root.id, timestamp)
            return ScanSummary(
                source_root_id=root.id,
                source_path=str(root_path),
                discovered=len(assets),
                added=added,
                updated=len(assets) - added,
                unavailable=unavailable,
                warnings=tuple(warnings),
            )
