"""Project photo inventory scanning and source-root management."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from photo_composition_designer.core.locations import Locations
from photo_composition_designer.core.photo import Photo
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.scan import find_image_files
from photo_composition_designer.project.models import PhotoAsset, SourceRoot
from photo_composition_designer.project.repositories import (
    PageRepository,
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


def _files_by_basename(files: list[Path]) -> dict[str, list[Path]]:
    """Group image files by basename for remap matching."""
    grouped: dict[str, list[Path]] = {}
    for path in files:
        grouped.setdefault(path.name, []).append(path)
    return grouped


@dataclass(frozen=True)
class ScanSummary:
    """Outcome of one source-root scan."""

    source_root_id: int
    source_path: str
    discovered: int
    added: int
    updated: int
    unavailable: int
    output_changed: bool = False
    warnings: tuple[str, ...] = ()
    duration_seconds: float = 0.0
    symlink_policy: str = "Symbolic links are skipped."

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary."""
        return {
            "source_root_id": self.source_root_id,
            "source_path": self.source_path,
            "discovered": self.discovered,
            "added": self.added,
            "updated": self.updated,
            "unavailable": self.unavailable,
            "output_changed": self.output_changed,
            "warnings": list(self.warnings),
            "duration_seconds": self.duration_seconds,
            "symlink_policy": self.symlink_policy,
        }


class InventoryService:
    """Manage source roots and the persisted photo inventory for a project."""

    def __init__(
        self,
        database: WorkspaceDatabase,
        *,
        locations: Locations | None = None,
    ) -> None:
        self._database = database
        self._locations = locations if locations is not None else Locations()

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
            try:
                root = repository.add(
                    project_id,
                    str(resolved),
                    active=False,
                    source_identity=str(resolved),
                    created_at=_now(),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"source directory is already configured: {resolved}") from exc
            if active:
                repository.set_active(project_id, root.id)
            stored = repository.get(root.id)
            if stored is None:
                raise RuntimeError("source root disappeared immediately after insert")
            return stored

    def set_active_source_root(self, project_id: int, source_root_id: int) -> None:
        """Make one source root active for the project."""
        with self._database.transaction() as connection:
            root = SourceRootRepository(connection).get(source_root_id)
            if root is None or root.project_id != project_id:
                raise ValueError("source root does not belong to this project")
            SourceRootRepository(connection).set_active(project_id, source_root_id)

    def remove_source_root(self, project_id: int, source_root_id: int) -> None:
        """Remove a source root that has no assigned photos.

        Photos and assignments are never removed together implicitly. A root
        with assigned photos must be unassigned first; unassigned inventory
        rows are removed with the root and can be rebuilt by scanning again.
        """
        with self._database.transaction() as connection:
            repository = SourceRootRepository(connection)
            root = repository.get(source_root_id)
            if root is None or root.project_id != project_id:
                raise ValueError("source root does not belong to this project")
            assigned = connection.execute(
                "SELECT COUNT(*) FROM assignments a "
                "JOIN photos p ON p.id = a.photo_id "
                "WHERE p.source_root_id = ?",
                (source_root_id,),
            ).fetchone()[0]
            if assigned:
                raise ValueError(
                    "source directory has assigned photos; unassign them before removing it"
                )
            repository.remove(source_root_id)

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
        started = time.monotonic()
        with self._database.transaction() as connection:
            return self._scan_in_transaction(connection, project_id, source_root_id, started)

    def _scan_in_transaction(
        self,
        connection,
        project_id: int,
        source_root_id: int | None,
        started: float,
    ) -> ScanSummary:
        """Scan one source root using an existing transaction."""
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
                photo = Photo(path, locations=self._locations.locations_dict)
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
        # A scan can change the photo bytes (mtime/size), the GPS coordinates or
        # availability. Any of these can change a page's rendered output, so the
        # cached previews keyed on the page revision must be invalidated. Digest
        # is not populated by the scanner, so mtime and file size are the
        # available content-change signals.
        new_assets = {asset.relative_path: asset for asset in assets}
        output_changed = False
        for relative_path, photo in existing.items():
            asset = new_assets.get(relative_path)
            if asset is None or (
                photo.gps_lat,
                photo.gps_lon,
                photo.available,
                photo.mtime,
                photo.file_size,
            ) != (
                asset.gps_lat,
                asset.gps_lon,
                asset.available,
                asset.mtime,
                asset.file_size,
            ):
                output_changed = True
                break
        if output_changed:
            PageRepository(connection).increment_revisions(project_id)

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
            output_changed=output_changed,
            warnings=tuple(warnings),
            duration_seconds=round(time.monotonic() - started, 3),
        )

    def preview_remap(
        self,
        project_id: int,
        *,
        source_root_id: int,
        new_root: str | Path,
    ) -> dict[str, Any]:
        """Preview relinking a source root to a new directory.

        Returns match counts and ambiguous basenames without mutating any state.
        A basename is ambiguous when the new root contains more than one file
        with that name; such photos are not silently remapped.
        """
        resolved = _resolve_directory(new_root)
        if not resolved.is_dir():
            raise ValueError(f"new source directory does not exist: {resolved}")

        with self._database.transaction() as connection:
            root = SourceRootRepository(connection).get(source_root_id)
            if root is None or root.project_id != project_id:
                raise ValueError("source root does not belong to this project")
            photos = [
                photo
                for photo in PhotoRepository(connection).list(project_id)
                if photo.source_root_id == root.id
            ]

        files = find_image_files(resolved)
        relative_paths = {path.relative_to(resolved).as_posix() for path in files}
        available_files = _files_by_basename(files)

        matched = 0
        ambiguous: list[str] = []
        missing: list[str] = []
        for photo in photos:
            if photo.relative_path in relative_paths:
                matched += 1
                continue
            candidates = available_files.get(photo.filename, [])
            if len(candidates) == 1:
                matched += 1
            elif len(candidates) > 1:
                ambiguous.append(photo.filename)
            else:
                missing.append(photo.filename)

        return {
            "source_root_id": root.id,
            "new_root": str(resolved),
            "total": len(photos),
            "matched": matched,
            "ambiguous": ambiguous,
            "missing": missing,
        }

    def apply_remap(
        self,
        project_id: int,
        *,
        source_root_id: int,
        new_root: str | Path,
    ) -> ScanSummary:
        """Atomically relink a source root to a new directory and rescan.

        Photos whose basename matches exactly one file in the new root are
        relinked. Ambiguous and missing basenames are left untouched and
        reported as warnings. Assignments are preserved.
        """
        resolved = _resolve_directory(new_root)
        if not resolved.is_dir():
            raise ValueError(f"new source directory does not exist: {resolved}")

        started = time.monotonic()
        with self._database.transaction() as connection:
            root_repository = SourceRootRepository(connection)
            root = root_repository.get(source_root_id)
            if root is None or root.project_id != project_id:
                raise ValueError("source root does not belong to this project")

            files = find_image_files(resolved)
            relative_paths = {path.relative_to(resolved).as_posix() for path in files}
            available_files = _files_by_basename(files)
            photo_repository = PhotoRepository(connection)
            photos = [
                photo
                for photo in photo_repository.list(project_id)
                if photo.source_root_id == root.id
            ]
            occupied = {photo.relative_path: photo.id for photo in photos}

            warnings: list[str] = []
            for photo in photos:
                if photo.relative_path in relative_paths:
                    continue
                candidates = available_files.get(photo.filename, [])
                if len(candidates) > 1:
                    warnings.append(f"{photo.filename}: ambiguous basename, left unchanged")
                    continue
                if not candidates:
                    warnings.append(f"{photo.filename}: missing in the new directory")
                    continue

                relative_path = candidates[0].relative_to(resolved).as_posix()
                owner = occupied.get(relative_path)
                if owner is not None and owner != photo.id:
                    warnings.append(
                        f"{photo.filename}: target path {relative_path} is already in use"
                    )
                    continue
                occupied.pop(photo.relative_path, None)
                occupied[relative_path] = photo.id
                photo_repository.update_relative_path(photo.id, relative_path)

            root_repository.update_path(root.id, str(resolved))
            summary = self._scan_in_transaction(connection, project_id, root.id, started)

        return replace(summary, warnings=summary.warnings + tuple(warnings))
