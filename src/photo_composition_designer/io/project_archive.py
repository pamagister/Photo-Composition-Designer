"""Reference-only project archive import and export."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime
from typing import Any

from photo_composition_designer.core.errors import ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.layouts.loader import LayoutValidationError, validate_layout
from photo_composition_designer.project.models import LayoutSlot, PhotoAsset
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
    SourceRootRepository,
)

ARCHIVE_VERSION = 1
MAX_ARCHIVE_SIZE = 50 * 1024 * 1024
MANIFEST_NAME = "project.json"


def export_project_archive(database: WorkspaceDatabase, project_id: int) -> bytes:
    """Create a `.pcd` archive containing project metadata, never photo files."""
    connection = database.connect()
    project = ProjectRepository(connection).get(project_id)
    if project is None:
        raise ProjectNotFoundError(f"project {project_id} does not exist")

    pages = PageRepository(connection).list(project_id)
    roots = SourceRootRepository(connection).list(project_id)
    photos = PhotoRepository(connection).list(project_id)
    assignments = AssignmentRepository(connection).list_by_project(project_id)
    layout_ids = {page.layout_id for page in pages if page.layout_id is not None}
    layout_repository = LayoutRepository(connection)
    layouts = [layout_repository.get_by_id(layout_id) for layout_id in sorted(layout_ids)]
    layouts = [layout for layout in layouts if layout is not None]

    manifest = {
        "format": "photo-composition-designer",
        "version": ARCHIVE_VERSION,
        "project": {
            "name": project.name,
            "calendar_year": project.calendar_year,
            "page_count": project.page_count,
            "settings": project.settings,
            "output_profile": project.output_profile,
            "import_metadata": project.import_metadata,
            "created_at": project.created_at,
        },
        "source_roots": [
            {
                "id": root.id,
                "path": root.path,
                "active": root.active,
                "last_scan_at": root.last_scan_at,
                "source_identity": root.source_identity,
                "created_at": root.created_at,
            }
            for root in roots
        ],
        "photos": [
            {
                "id": photo.id,
                "source_root_id": photo.source_root_id,
                "relative_path": photo.relative_path,
                "filename": photo.filename,
                "file_size": photo.file_size,
                "mtime": photo.mtime,
                "digest": photo.digest,
                "width": photo.width,
                "height": photo.height,
                "captured_at": photo.captured_at,
                "gps_lat": photo.gps_lat,
                "gps_lon": photo.gps_lon,
                "available": photo.available,
                "created_at": photo.created_at,
            }
            for photo in photos
        ],
        "layouts": [
            {
                "id": layout.id,
                "key": layout.key,
                "version": layout.version,
                "name": layout.name,
                "created_at": layout.created_at,
                "slots": [
                    {
                        "id": slot.id,
                        "slot_key": slot.slot_key,
                        "position": slot.position,
                        "x": slot.x,
                        "y": slot.y,
                        "width": slot.width,
                        "height": slot.height,
                        "z_index": slot.z_index,
                        "crop_mode": slot.crop_mode,
                    }
                    for slot in layout.slots
                ],
            }
            for layout in layouts
        ],
        "pages": [
            {
                "id": page.id,
                "page_index": page.page_index,
                "start_date": page.start_date,
                "end_date": page.end_date,
                "description": page.description,
                "layout_id": page.layout_id,
                "layout_version": page.layout_version,
                "hide_local_map": page.hide_local_map,
                "hide_calendar_strip": page.hide_calendar_strip,
                "hide_description": page.hide_description,
                "created_at": page.created_at,
            }
            for page in pages
        ],
        "assignments": [
            {
                "page_id": assignment.page_id,
                "slot_id": assignment.slot_id,
                "photo_id": assignment.photo_id,
                "crop_zoom": assignment.crop_zoom,
                "crop_focus_x": assignment.crop_focus_x,
                "crop_focus_y": assignment.crop_focus_y,
                "created_at": assignment.created_at,
            }
            for assignment in assignments
        ],
    }
    encoded = json.dumps(manifest, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_ARCHIVE_SIZE:
        raise ValueError("project metadata is too large to export")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, encoded)
    return output.getvalue()


def _read_manifest(archive_data: bytes) -> dict[str, Any]:
    if len(archive_data) > MAX_ARCHIVE_SIZE:
        raise ValueError("project archive exceeds the size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            members = archive.infolist()
            if len(members) != 1 or members[0].filename != MANIFEST_NAME:
                raise ValueError("project archive must contain only project.json")
            if members[0].file_size > MAX_ARCHIVE_SIZE:
                raise ValueError("project metadata exceeds the size limit")
            manifest = json.loads(archive.read(members[0]))
    except (
        OSError,
        RecursionError,
        RuntimeError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as error:
        raise ValueError("invalid project archive") from error
    if not isinstance(manifest, dict):
        raise ValueError("invalid project archive manifest")
    if manifest.get("format") != "photo-composition-designer":
        raise ValueError("unsupported project archive format")
    if manifest.get("version") != ARCHIVE_VERSION:
        raise ValueError("unsupported project archive version")
    required = ("project", "source_roots", "photos", "layouts", "pages", "assignments")
    if any(key not in manifest for key in required):
        raise ValueError("project archive is missing required data")
    if not isinstance(manifest["project"], dict) or any(
        not isinstance(manifest[key], list) for key in required[1:]
    ):
        raise ValueError("project archive contains invalid data")
    _validate_manifest(manifest)
    return manifest


def _validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate identifiers and references before starting a database transaction."""
    project = manifest["project"]
    if not isinstance(project.get("name"), str) or not project["name"].strip():
        raise ValueError("project archive has an invalid project name")
    if not isinstance(project.get("settings", {}), dict) or not isinstance(
        project.get("output_profile", {}), dict
    ):
        raise ValueError("project archive has invalid project settings")
    if not isinstance(project.get("import_metadata", {}), dict):
        raise ValueError("project archive has invalid import metadata")
    calendar_year = project.get("calendar_year")
    if calendar_year is not None and (
        not isinstance(calendar_year, int) or isinstance(calendar_year, bool)
    ):
        raise ValueError("project archive has an invalid calendar year")
    try:
        OutputProfile.from_dict(project.get("output_profile", {}))
    except (TypeError, ValueError) as error:
        raise ValueError("project archive has an invalid output profile") from error

    def index_by_id(rows: list[dict[str, Any]], label: str) -> dict[int, dict[str, Any]]:
        indexed: dict[int, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"project archive contains an invalid {label}")
            identifier = row.get("id")
            if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 1:
                raise ValueError(f"project archive contains an invalid {label} identifier")
            if identifier in indexed:
                raise ValueError(f"project archive contains duplicate {label} identifiers")
            indexed[identifier] = row
        return indexed

    roots = index_by_id(manifest["source_roots"], "source root")
    photos = index_by_id(manifest["photos"], "photo")
    layouts = index_by_id(manifest["layouts"], "layout")
    pages = index_by_id(manifest["pages"], "page")
    for root in roots.values():
        if not isinstance(root.get("path"), str) or not root["path"]:
            raise ValueError("project archive contains an invalid source root")
        if not isinstance(root.get("active"), bool):
            raise ValueError("project archive contains an invalid source-root status")
    page_count = project.get("page_count")
    if (
        not isinstance(page_count, int)
        or isinstance(page_count, bool)
        or page_count < 1
        or len(pages) != page_count
    ):
        raise ValueError("project archive page count does not match its pages")
    if sum(bool(root.get("active")) for root in roots.values()) > 1:
        raise ValueError("project archive contains multiple active source roots")

    for photo in photos.values():
        root_id = photo.get("source_root_id")
        if not isinstance(root_id, int) or isinstance(root_id, bool) or root_id not in roots:
            raise ValueError("project archive photo references an unknown source root")
        if not isinstance(photo.get("relative_path"), str) or not photo["relative_path"]:
            raise ValueError("project archive contains an invalid photo path")

    slot_ids: set[int] = set()
    for layout in layouts.values():
        slots = layout.get("slots")
        if not isinstance(slots, list) or any(not isinstance(slot, dict) for slot in slots):
            raise ValueError("project archive contains an invalid layout")
        if not isinstance(layout.get("version"), int) or isinstance(layout.get("version"), bool):
            raise ValueError("project archive contains an invalid layout version")
        layout_data = {
            "key": layout.get("key"),
            "version": layout.get("version"),
            "name": layout.get("name"),
            "slots": [
                {
                    "key": slot.get("slot_key"),
                    "x": slot.get("x"),
                    "y": slot.get("y"),
                    "width": slot.get("width"),
                    "height": slot.get("height"),
                    "crop_mode": slot.get("crop_mode"),
                }
                for slot in slots
            ],
        }
        try:
            validate_layout(layout_data)
        except (LayoutValidationError, TypeError, ValueError) as error:
            raise ValueError(f"project archive contains an invalid layout: {error}") from error
        positions: set[int] = set()
        for slot in slots:
            slot_id = slot.get("id")
            position = slot.get("position")
            if (
                not isinstance(slot_id, int)
                or isinstance(slot_id, bool)
                or slot_id < 1
                or slot_id in slot_ids
                or not isinstance(position, int)
                or position < 0
                or position in positions
            ):
                raise ValueError("project archive contains invalid layout slot identifiers")
            slot_ids.add(slot_id)
            positions.add(position)

    ordered_pages = sorted(pages.values(), key=lambda page: page.get("page_index", -1))
    for index, page in enumerate(ordered_pages):
        page_index = page.get("page_index")
        if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index != index:
            raise ValueError("project archive page indexes are invalid")
        try:
            page_start = date.fromisoformat(page["start_date"])
            page_end = date.fromisoformat(page["end_date"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("project archive contains an invalid page date") from error
        if page_end < page_start:
            raise ValueError("project archive page end date precedes its start date")
        layout_id = page.get("layout_id")
        if layout_id is not None:
            if (
                not isinstance(layout_id, int)
                or isinstance(layout_id, bool)
                or layout_id not in layouts
            ):
                raise ValueError("project archive page references an unknown layout")
            layout_version = page.get("layout_version")
            if (
                not isinstance(layout_version, int)
                or isinstance(layout_version, bool)
                or layout_version != layouts[layout_id].get("version")
            ):
                raise ValueError("project archive page has an invalid layout version")

    occupied_slots: set[tuple[int, int]] = set()
    for assignment in manifest["assignments"]:
        if not isinstance(assignment, dict):
            raise ValueError("project archive contains an invalid assignment")
        page_id = assignment.get("page_id")
        photo_id = assignment.get("photo_id")
        slot_id = assignment.get("slot_id")
        if not all(
            isinstance(identifier, int) and not isinstance(identifier, bool)
            for identifier in (page_id, photo_id, slot_id)
        ):
            raise ValueError("project archive assignment identifiers are invalid")
        if page_id not in pages or photo_id not in photos or slot_id not in slot_ids:
            raise ValueError("project archive assignment references unknown data")
        page = pages[page_id]
        layout_id = page.get("layout_id")
        layout = layouts.get(layout_id)
        if layout is None or not any(slot.get("id") == slot_id for slot in layout.get("slots", [])):
            raise ValueError("project archive assignment slot does not match its page layout")
        unique_slot = (page_id, slot_id)
        if unique_slot in occupied_slots:
            raise ValueError("project archive assigns multiple photos to one slot")
        occupied_slots.add(unique_slot)


def _same_layout(existing, archive_layout: dict[str, Any]) -> bool:
    slots = archive_layout["slots"]
    return (
        existing.name == archive_layout["name"]
        and len(existing.slots) == len(slots)
        and all(
            (
                stored.slot_key,
                stored.position,
                stored.x,
                stored.y,
                stored.width,
                stored.height,
                stored.z_index,
                stored.crop_mode,
            )
            == (
                imported["slot_key"],
                imported["position"],
                imported["x"],
                imported["y"],
                imported["width"],
                imported["height"],
                imported["z_index"],
                imported["crop_mode"],
            )
            for stored, imported in zip(existing.slots, slots, strict=True)
        )
    )


def import_project_archive(
    database: WorkspaceDatabase,
    archive_data: bytes,
    *,
    name: str | None = None,
):
    """Import a reference-only project archive into the workspace."""
    manifest = _read_manifest(archive_data)
    project_data = manifest["project"]
    project_name = (name or project_data.get("name", "")).strip()
    if not project_name:
        raise ValueError("project name must not be empty")

    timestamp = datetime.now(UTC).isoformat()
    with database.transaction() as connection:
        project = ProjectRepository(connection).create(
            name=project_name,
            page_count=int(project_data["page_count"]),
            calendar_year=project_data.get("calendar_year"),
            settings=project_data.get("settings", {}),
            output_profile=project_data.get("output_profile", {}),
            import_metadata=project_data.get("import_metadata", {}),
            created_at=timestamp,
        )

        root_ids: dict[int, int] = {}
        root_repository = SourceRootRepository(connection)
        for root in manifest["source_roots"]:
            old_id = int(root["id"])
            imported = root_repository.add(
                project.id,
                str(root["path"]),
                active=bool(root["active"]),
                source_identity=root.get("source_identity"),
                last_scan_at=root.get("last_scan_at"),
                created_at=timestamp,
            )
            root_ids[old_id] = imported.id

        photo_repository = PhotoRepository(connection)
        old_photo_data = manifest["photos"]
        photo_repository.upsert_many(
            PhotoAsset(
                id=0,
                project_id=project.id,
                source_root_id=root_ids[int(photo["source_root_id"])],
                relative_path=str(photo["relative_path"]),
                filename=str(photo["filename"]),
                file_size=int(photo["file_size"]),
                mtime=float(photo["mtime"]) if photo.get("mtime") is not None else None,
                digest=photo.get("digest"),
                width=int(photo["width"]),
                height=int(photo["height"]),
                captured_at=photo.get("captured_at"),
                gps_lat=float(photo["gps_lat"]) if photo.get("gps_lat") is not None else None,
                gps_lon=float(photo["gps_lon"]) if photo.get("gps_lon") is not None else None,
                available=bool(photo["available"]),
                created_at=timestamp,
            )
            for photo in old_photo_data
        )
        photo_ids: dict[int, int] = {}
        for photo in old_photo_data:
            imported_photo = connection.execute(
                "SELECT id FROM photos WHERE project_id = ? AND source_root_id = ? "
                "AND relative_path = ?",
                (
                    project.id,
                    root_ids[int(photo["source_root_id"])],
                    photo["relative_path"],
                ),
            ).fetchone()
            if imported_photo is None:
                raise ValueError("photo inventory could not be imported")
            photo_ids[int(photo["id"])] = int(imported_photo["id"])

        layout_repository = LayoutRepository(connection)
        layout_ids: dict[int, int] = {}
        slot_ids: dict[int, int] = {}
        for layout in manifest["layouts"]:
            old_id = int(layout["id"])
            key = str(layout["key"])
            version = int(layout["version"])
            existing = layout_repository.get(key, version)
            if existing is not None and not _same_layout(existing, layout):
                fingerprint = hashlib.sha256(
                    json.dumps(
                        {"name": layout["name"], "slots": layout["slots"]},
                        sort_keys=True,
                    ).encode()
                ).hexdigest()[:10]
                key = f"{key[:24]}_import_{project.id}_{fingerprint}"
                existing = layout_repository.get(key, version)
            if existing is None:
                created = layout_repository.add(
                    key,
                    version,
                    str(layout["name"]),
                    [
                        LayoutSlot(
                            id=0,
                            layout_id=0,
                            slot_key=str(slot["slot_key"]),
                            position=int(slot["position"]),
                            x=float(slot["x"]),
                            y=float(slot["y"]),
                            width=float(slot["width"]),
                            height=float(slot["height"]),
                            z_index=int(slot["z_index"]),
                            crop_mode=str(slot["crop_mode"]),
                        )
                        for slot in layout["slots"]
                    ],
                    created_at=timestamp,
                )
            else:
                created = existing
            layout_ids[old_id] = created.id
            for old_slot, new_slot in zip(layout["slots"], created.slots, strict=True):
                slot_ids[int(old_slot["id"])] = new_slot.id

        page_ids: dict[int, int] = {}
        page_repository = PageRepository(connection)
        for page in manifest["pages"]:
            old_id = int(page["id"])
            old_layout_id = page.get("layout_id")
            layout_id = layout_ids[int(old_layout_id)] if old_layout_id is not None else None
            created = page_repository.create(
                project.id,
                int(page["page_index"]),
                str(page["start_date"]),
                str(page["end_date"]),
                description=str(page.get("description", "")),
                layout_id=layout_id,
                layout_version=page.get("layout_version"),
                hide_local_map=bool(page.get("hide_local_map", False)),
                hide_calendar_strip=bool(page.get("hide_calendar_strip", False)),
                hide_description=bool(page.get("hide_description", False)),
                created_at=timestamp,
            )
            page_ids[old_id] = created.id

        assignment_repository = AssignmentRepository(connection)
        for assignment in manifest["assignments"]:
            assignment_repository.assign(
                project.id,
                page_ids[int(assignment["page_id"])],
                slot_ids[int(assignment["slot_id"])],
                photo_ids[int(assignment["photo_id"])],
                crop_zoom=float(assignment["crop_zoom"]),
                crop_focus_x=float(assignment["crop_focus_x"]),
                crop_focus_y=float(assignment["crop_focus_y"]),
                created_at=timestamp,
            )

    return project


__all__ = [
    "ARCHIVE_VERSION",
    "MAX_ARCHIVE_SIZE",
    "export_project_archive",
    "import_project_archive",
]
