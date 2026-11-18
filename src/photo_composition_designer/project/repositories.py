"""SQLite repositories for project data.

All SQL lives in this module. Domain models and application services do not
build queries directly.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from photo_composition_designer.core.errors import (
    CrossProjectAssignmentError,
    DuplicateAssignmentError,
    DuplicatePhotoAssignmentError,
    DuplicateSlotAssignmentError,
    ProjectNotFoundError,
    SlotLayoutMismatchError,
)
from photo_composition_designer.project.models import (
    CalendarPage,
    LayoutDefinition,
    LayoutSlot,
    PhotoAsset,
    PhotoAssignment,
    Project,
    SourceRoot,
)


def _now() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


def _dump_json(value: dict[str, Any]) -> str:
    """Serialize a settings mapping deterministically."""
    return json.dumps(value, sort_keys=True)


def _load_json(value: str | None) -> dict[str, Any]:
    """Deserialize a settings mapping."""
    return json.loads(value) if value else {}


def _require_row_id(cursor: sqlite3.Cursor) -> int:
    """Return a cursor's inserted row ID or fail loudly."""
    row_id = cursor.lastrowid
    if row_id is None:
        raise RuntimeError("SQLite did not return an inserted row id")
    return int(row_id)


class ProjectRepository:
    """Persistence for projects and their settings snapshots."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> Project:
        return Project(
            id=int(row["id"]),
            name=str(row["name"]),
            calendar_year=int(row["calendar_year"]) if row["calendar_year"] is not None else None,
            page_count=int(row["page_count"]),
            settings=_load_json(row["settings_json"]),
            output_profile=_load_json(row["output_profile_json"]),
            import_metadata=_load_json(row["import_metadata_json"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def create(
        self,
        *,
        name: str,
        page_count: int,
        calendar_year: int | None,
        settings: dict[str, Any],
        output_profile: dict[str, Any],
        import_metadata: dict[str, Any],
        created_at: str | None = None,
    ) -> Project:
        """Insert a project row and return the stored aggregate."""
        timestamp = created_at or _now()
        cursor = self._connection.execute(
            "INSERT INTO projects("
            "name, calendar_year, page_count, settings_json, output_profile_json, "
            "import_metadata_json, created_at, updated_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                calendar_year,
                page_count,
                _dump_json(settings),
                _dump_json(output_profile),
                _dump_json(import_metadata),
                timestamp,
                timestamp,
            ),
        )
        project = self.get(_require_row_id(cursor))
        if project is None:
            raise RuntimeError("project disappeared immediately after insert")
        return project

    def get(self, project_id: int) -> Project | None:
        """Return one project or ``None``."""
        row = self._connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return self._row_to_project(row) if row is not None else None

    def list(self) -> list[Project]:
        """Return all projects ordered by ID."""
        rows = self._connection.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [self._row_to_project(row) for row in rows]

    def update(
        self,
        project_id: int,
        *,
        name: str | None = None,
        settings: dict[str, Any] | None = None,
        output_profile: dict[str, Any] | None = None,
        updated_at: str | None = None,
    ) -> Project:
        """Update mutable project fields and return the new state."""
        current = self.get(project_id)
        if current is None:
            raise ProjectNotFoundError(f"project {project_id} does not exist")

        self._connection.execute(
            "UPDATE projects SET name = ?, settings_json = ?, output_profile_json = ?, "
            "updated_at = ? WHERE id = ?",
            (
                current.name if name is None else name,
                _dump_json(current.settings if settings is None else settings),
                _dump_json(current.output_profile if output_profile is None else output_profile),
                updated_at or _now(),
                project_id,
            ),
        )
        updated = self.get(project_id)
        if updated is None:
            raise ProjectNotFoundError(f"project {project_id} disappeared during update")
        return updated

    def delete(self, project_id: int) -> None:
        """Delete a project and cascade its project-owned rows."""
        self._connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))


class SourceRootRepository:
    """Persistence for project source roots."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def _row_to_source_root(row: sqlite3.Row) -> SourceRoot:
        return SourceRoot(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            path=str(row["path"]),
            active=bool(row["active"]),
            last_scan_at=str(row["last_scan_at"]) if row["last_scan_at"] is not None else None,
            source_identity=(
                str(row["source_identity"]) if row["source_identity"] is not None else None
            ),
            created_at=str(row["created_at"]),
        )

    def add(
        self,
        project_id: int,
        path: str,
        *,
        active: bool = False,
        source_identity: str | None = None,
        created_at: str | None = None,
    ) -> SourceRoot:
        """Add a source root to a project."""
        cursor = self._connection.execute(
            "INSERT INTO source_roots("
            "project_id, path, active, source_identity, created_at"
            ") VALUES(?, ?, ?, ?, ?)",
            (project_id, path, int(active), source_identity, created_at or _now()),
        )
        root = self.get(_require_row_id(cursor))
        if root is None:
            raise RuntimeError("source root disappeared immediately after insert")
        return root

    def get(self, source_root_id: int) -> SourceRoot | None:
        """Return one source root or ``None``."""
        row = self._connection.execute(
            "SELECT * FROM source_roots WHERE id = ?", (source_root_id,)
        ).fetchone()
        return self._row_to_source_root(row) if row is not None else None

    def list(self, project_id: int) -> list[SourceRoot]:
        """Return all source roots for a project ordered by ID."""
        rows = self._connection.execute(
            "SELECT * FROM source_roots WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
        return [self._row_to_source_root(row) for row in rows]

    def get_active(self, project_id: int) -> SourceRoot | None:
        """Return the active source root for a project, if any."""
        row = self._connection.execute(
            "SELECT * FROM source_roots WHERE project_id = ? AND active = 1", (project_id,)
        ).fetchone()
        return self._row_to_source_root(row) if row is not None else None

    def set_active(self, project_id: int, source_root_id: int) -> None:
        """Make exactly one source root active for a project."""
        self._connection.execute(
            "UPDATE source_roots SET active = 0 WHERE project_id = ?", (project_id,)
        )
        cursor = self._connection.execute(
            "UPDATE source_roots SET active = 1 WHERE id = ? AND project_id = ?",
            (source_root_id, project_id),
        )
        if cursor.rowcount != 1:
            raise ProjectNotFoundError(
                f"source root {source_root_id} does not belong to project {project_id}"
            )

    def update_scan(self, source_root_id: int, last_scan_at: str | None = None) -> None:
        """Record the last successful scan timestamp."""
        self._connection.execute(
            "UPDATE source_roots SET last_scan_at = ? WHERE id = ?",
            (last_scan_at or _now(), source_root_id),
        )

    def update_path(self, source_root_id: int, path: str) -> None:
        """Point a source root at a new directory.

        Raises:
            ProjectNotFoundError: If the source root does not exist.
        """
        cursor = self._connection.execute(
            "UPDATE source_roots SET path = ? WHERE id = ?",
            (path, source_root_id),
        )
        if cursor.rowcount != 1:
            raise ProjectNotFoundError(f"source root {source_root_id} does not exist")


class PhotoRepository:
    """Persistence for project photo inventory."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def _row_to_photo(row: sqlite3.Row) -> PhotoAsset:
        return PhotoAsset(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            source_root_id=int(row["source_root_id"]),
            relative_path=str(row["relative_path"]),
            filename=str(row["filename"]),
            file_size=int(row["file_size"]),
            mtime=float(row["mtime"]) if row["mtime"] is not None else None,
            digest=str(row["digest"]) if row["digest"] is not None else None,
            width=int(row["width"]),
            height=int(row["height"]),
            captured_at=str(row["captured_at"]) if row["captured_at"] is not None else None,
            gps_lat=float(row["gps_lat"]) if row["gps_lat"] is not None else None,
            gps_lon=float(row["gps_lon"]) if row["gps_lon"] is not None else None,
            available=bool(row["available"]),
            created_at=str(row["created_at"]),
        )

    def upsert_many(self, photos: Iterable[PhotoAsset]) -> int:
        """Insert or refresh inventory rows, keyed by project/root/relative path."""
        sql = (
            "INSERT INTO photos("
            "project_id, source_root_id, relative_path, filename, file_size, mtime, digest, "
            "width, height, captured_at, gps_lat, gps_lon, available, created_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, source_root_id, relative_path) DO UPDATE SET "
            "filename = excluded.filename, file_size = excluded.file_size, "
            "mtime = excluded.mtime, digest = excluded.digest, width = excluded.width, "
            "height = excluded.height, captured_at = excluded.captured_at, "
            "gps_lat = excluded.gps_lat, gps_lon = excluded.gps_lon, "
            "available = excluded.available"
        )
        count = 0
        for photo in photos:
            self._connection.execute(
                sql,
                (
                    photo.project_id,
                    photo.source_root_id,
                    photo.relative_path,
                    photo.filename,
                    photo.file_size,
                    photo.mtime,
                    photo.digest,
                    photo.width,
                    photo.height,
                    photo.captured_at,
                    photo.gps_lat,
                    photo.gps_lon,
                    int(photo.available),
                    photo.created_at,
                ),
            )
            count += 1
        return count

    def get(self, photo_id: int) -> PhotoAsset | None:
        """Return one photo asset or ``None``."""
        row = self._connection.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
        return self._row_to_photo(row) if row is not None else None

    def list(self, project_id: int, *, available_only: bool = False) -> list[PhotoAsset]:
        """Return project photos ordered by relative path."""
        sql = "SELECT * FROM photos WHERE project_id = ?"
        if available_only:
            sql += " AND available = 1"
        sql += " ORDER BY relative_path"
        rows = self._connection.execute(sql, (project_id,)).fetchall()
        return [self._row_to_photo(row) for row in rows]

    def list_unassigned(self, project_id: int) -> list[PhotoAsset]:
        """Return photos that have no assignment in the project."""
        rows = self._connection.execute(
            "SELECT p.* FROM photos p "
            "LEFT JOIN assignments a ON a.photo_id = p.id AND a.project_id = p.project_id "
            "WHERE p.project_id = ? AND a.id IS NULL "
            "ORDER BY p.relative_path",
            (project_id,),
        ).fetchall()
        return [self._row_to_photo(row) for row in rows]

    def set_availability(self, photo_id: int, available: bool) -> None:
        """Mark a photo as available or unavailable."""
        self._connection.execute(
            "UPDATE photos SET available = ? WHERE id = ?", (int(available), photo_id)
        )


class PageRepository:
    """Persistence for calendar pages."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def _row_to_page(row: sqlite3.Row) -> CalendarPage:
        return CalendarPage(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            page_index=int(row["page_index"]),
            start_date=str(row["start_date"]),
            end_date=str(row["end_date"]),
            description=str(row["description"]),
            layout_id=int(row["layout_id"]) if row["layout_id"] is not None else None,
            layout_version=(
                int(row["layout_version"]) if row["layout_version"] is not None else None
            ),
            render_revision=int(row["render_revision"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def create(
        self,
        project_id: int,
        page_index: int,
        start_date: str,
        end_date: str,
        *,
        description: str = "",
        layout_id: int | None = None,
        layout_version: int | None = None,
        created_at: str | None = None,
    ) -> CalendarPage:
        """Insert one page."""
        timestamp = created_at or _now()
        cursor = self._connection.execute(
            "INSERT INTO pages("
            "project_id, page_index, start_date, end_date, description, layout_id, "
            "layout_version, render_revision, created_at, updated_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (
                project_id,
                page_index,
                start_date,
                end_date,
                description,
                layout_id,
                layout_version,
                timestamp,
                timestamp,
            ),
        )
        page = self.get(_require_row_id(cursor))
        if page is None:
            raise RuntimeError("page disappeared immediately after insert")
        return page

    def get(self, page_id: int) -> CalendarPage | None:
        """Return one page or ``None``."""
        row = self._connection.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        return self._row_to_page(row) if row is not None else None

    def list(self, project_id: int) -> list[CalendarPage]:
        """Return project pages ordered by page index."""
        rows = self._connection.execute(
            "SELECT * FROM pages WHERE project_id = ? ORDER BY page_index", (project_id,)
        ).fetchall()
        return [self._row_to_page(row) for row in rows]

    def update_description(self, page_id: int, description: str) -> CalendarPage:
        """Update a page description and increment its render revision."""
        self._connection.execute(
            "UPDATE pages SET description = ?, render_revision = render_revision + 1, "
            "updated_at = ? WHERE id = ?",
            (description, _now(), page_id),
        )
        page = self.get(page_id)
        if page is None:
            raise ProjectNotFoundError(f"page {page_id} does not exist")
        return page

    def set_layout(
        self, page_id: int, layout_id: int | None, layout_version: int | None
    ) -> CalendarPage:
        """Set the layout snapshot for a page and increment its render revision."""
        self._connection.execute(
            "UPDATE pages SET layout_id = ?, layout_version = ?, "
            "render_revision = render_revision + 1, updated_at = ? WHERE id = ?",
            (layout_id, layout_version, _now(), page_id),
        )
        page = self.get(page_id)
        if page is None:
            raise ProjectNotFoundError(f"page {page_id} does not exist")
        return page

    def increment_revision(self, page_id: int) -> None:
        """Increment the page render revision."""
        self._connection.execute(
            "UPDATE pages SET render_revision = render_revision + 1, updated_at = ? WHERE id = ?",
            (_now(), page_id),
        )


class LayoutRepository:
    """Persistence for immutable layout definitions."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def _row_to_slot(row: sqlite3.Row) -> LayoutSlot:
        return LayoutSlot(
            id=int(row["id"]),
            layout_id=int(row["layout_id"]),
            slot_key=str(row["slot_key"]),
            position=int(row["position"]),
            x=float(row["x"]),
            y=float(row["y"]),
            width=float(row["width"]),
            height=float(row["height"]),
            z_index=int(row["z_index"]),
            crop_mode=str(row["crop_mode"]),
        )

    def _row_to_layout(self, row: sqlite3.Row) -> LayoutDefinition:
        slot_rows = self._connection.execute(
            "SELECT * FROM layout_slots WHERE layout_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        return LayoutDefinition(
            id=int(row["id"]),
            key=str(row["key"]),
            version=int(row["version"]),
            name=str(row["name"]),
            slots=[self._row_to_slot(slot_row) for slot_row in slot_rows],
            created_at=str(row["created_at"]),
        )

    def add(
        self,
        key: str,
        version: int,
        name: str,
        slots: list[LayoutSlot],
        *,
        created_at: str | None = None,
    ) -> LayoutDefinition:
        """Insert an immutable layout and its slots."""
        cursor = self._connection.execute(
            "INSERT INTO layouts(key, version, name, created_at) VALUES(?, ?, ?, ?)",
            (key, version, name, created_at or _now()),
        )
        layout_id = _require_row_id(cursor)
        for slot in slots:
            self._connection.execute(
                "INSERT INTO layout_slots("
                "layout_id, slot_key, position, x, y, width, height, z_index, crop_mode"
                ") VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    layout_id,
                    slot.slot_key,
                    slot.position,
                    slot.x,
                    slot.y,
                    slot.width,
                    slot.height,
                    slot.z_index,
                    slot.crop_mode,
                ),
            )
        layout = self.get_by_id(layout_id)
        if layout is None:
            raise RuntimeError("layout disappeared immediately after insert")
        return layout

    def get(self, key: str, version: int) -> LayoutDefinition | None:
        """Return a layout by stable key and version."""
        row = self._connection.execute(
            "SELECT * FROM layouts WHERE key = ? AND version = ?", (key, version)
        ).fetchone()
        return self._row_to_layout(row) if row is not None else None

    def get_by_id(self, layout_id: int) -> LayoutDefinition | None:
        """Return a layout by row ID."""
        row = self._connection.execute(
            "SELECT * FROM layouts WHERE id = ?", (layout_id,)
        ).fetchone()
        return self._row_to_layout(row) if row is not None else None

    def list(self) -> list[LayoutDefinition]:
        """Return all layouts ordered by key and version."""
        rows = self._connection.execute("SELECT * FROM layouts ORDER BY key, version").fetchall()
        return [self._row_to_layout(row) for row in rows]


class AssignmentRepository:
    """Persistence for photo-to-slot assignments."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def _row_to_assignment(row: sqlite3.Row) -> PhotoAssignment:
        return PhotoAssignment(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            page_id=int(row["page_id"]),
            slot_id=int(row["slot_id"]),
            photo_id=int(row["photo_id"]),
            crop_zoom=float(row["crop_zoom"]),
            crop_focus_x=float(row["crop_focus_x"]),
            crop_focus_y=float(row["crop_focus_y"]),
            created_at=str(row["created_at"]),
        )

    def _validate(self, project_id: int, page_id: int, slot_id: int, photo_id: int) -> None:
        """Validate project and layout consistency before inserting."""
        photo_row = self._connection.execute(
            "SELECT project_id FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()
        if photo_row is None or int(photo_row["project_id"]) != project_id:
            raise CrossProjectAssignmentError(
                f"photo {photo_id} does not belong to project {project_id}"
            )

        page_row = self._connection.execute(
            "SELECT project_id, layout_id FROM pages WHERE id = ?", (page_id,)
        ).fetchone()
        if page_row is None or int(page_row["project_id"]) != project_id:
            raise CrossProjectAssignmentError(
                f"page {page_id} does not belong to project {project_id}"
            )

        slot_row = self._connection.execute(
            "SELECT layout_id FROM layout_slots WHERE id = ?", (slot_id,)
        ).fetchone()
        if slot_row is None or page_row["layout_id"] != slot_row["layout_id"]:
            raise SlotLayoutMismatchError(
                f"slot {slot_id} does not belong to the layout of page {page_id}"
            )

        if (
            self._connection.execute(
                "SELECT 1 FROM assignments WHERE project_id = ? AND photo_id = ?",
                (project_id, photo_id),
            ).fetchone()
            is not None
        ):
            raise DuplicatePhotoAssignmentError(
                f"photo {photo_id} is already assigned in project {project_id}"
            )

        if (
            self._connection.execute(
                "SELECT 1 FROM assignments WHERE page_id = ? AND slot_id = ?",
                (page_id, slot_id),
            ).fetchone()
            is not None
        ):
            raise DuplicateSlotAssignmentError(
                f"slot {slot_id} on page {page_id} is already occupied"
            )

    def assign(
        self,
        project_id: int,
        page_id: int,
        slot_id: int,
        photo_id: int,
        *,
        crop_zoom: float = 1.0,
        crop_focus_x: float = 0.5,
        crop_focus_y: float = 0.5,
        created_at: str | None = None,
    ) -> PhotoAssignment:
        """Assign a photo to a slot after validating all invariants."""
        self._validate(project_id, page_id, slot_id, photo_id)
        try:
            cursor = self._connection.execute(
                "INSERT INTO assignments("
                "project_id, page_id, slot_id, photo_id, crop_zoom, crop_focus_x, "
                "crop_focus_y, created_at"
                ") VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    page_id,
                    slot_id,
                    photo_id,
                    crop_zoom,
                    crop_focus_x,
                    crop_focus_y,
                    created_at or _now(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateAssignmentError("assignment violates a uniqueness constraint") from exc

        assignment = self.get(_require_row_id(cursor))
        if assignment is None:
            raise RuntimeError("assignment disappeared immediately after insert")
        return assignment

    def get(self, assignment_id: int) -> PhotoAssignment | None:
        """Return one assignment or ``None``."""
        row = self._connection.execute(
            "SELECT * FROM assignments WHERE id = ?", (assignment_id,)
        ).fetchone()
        return self._row_to_assignment(row) if row is not None else None

    def remove(self, assignment_id: int) -> bool:
        """Delete one assignment, returning whether a row was removed."""
        cursor = self._connection.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
        return cursor.rowcount > 0

    def remove_by_page_slot(self, page_id: int, slot_id: int) -> bool:
        """Delete the assignment on a page slot, if present."""
        cursor = self._connection.execute(
            "DELETE FROM assignments WHERE page_id = ? AND slot_id = ?", (page_id, slot_id)
        )
        return cursor.rowcount > 0

    def update_crop(
        self,
        assignment_id: int,
        *,
        crop_zoom: float,
        crop_focus_x: float,
        crop_focus_y: float,
    ) -> None:
        """Update the per-assignment crop settings."""
        cursor = self._connection.execute(
            "UPDATE assignments SET crop_zoom = ?, crop_focus_x = ?, crop_focus_y = ? WHERE id = ?",
            (crop_zoom, crop_focus_x, crop_focus_y, assignment_id),
        )
        if cursor.rowcount != 1:
            raise ProjectNotFoundError(f"assignment {assignment_id} does not exist")

    def list_by_page(self, page_id: int) -> list[PhotoAssignment]:
        """Return all assignments for a page ordered by slot ID."""
        rows = self._connection.execute(
            "SELECT * FROM assignments WHERE page_id = ? ORDER BY slot_id", (page_id,)
        ).fetchall()
        return [self._row_to_assignment(row) for row in rows]

    def list_by_project(self, project_id: int) -> list[PhotoAssignment]:
        """Return all assignments for a project ordered by ID."""
        rows = self._connection.execute(
            "SELECT * FROM assignments WHERE project_id = ? ORDER BY id", (project_id,)
        ).fetchall()
        return [self._row_to_assignment(row) for row in rows]

    def list(self, project_id: int) -> list[PhotoAssignment]:
        """Return all assignments for a project (alias for ``list_by_project``)."""
        return self.list_by_project(project_id)

    def clear_for_project(self, project_id: int) -> None:
        """Remove every assignment for a project in one statement."""
        self._connection.execute("DELETE FROM assignments WHERE project_id = ?", (project_id,))
