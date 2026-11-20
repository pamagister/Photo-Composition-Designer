"""Shared helpers for the render-performance benchmark.

Builds a synthetic project with ``slots`` slots per page, one real JPEG per
slot (copied from ``images/``), an optional GPS-tagged subset, and the full
assignment graph. The profile is the application default (216x154 mm @ 300 dpi)
so measurements match real output.

This module is imported by ``scripts/benchmark_render.py`` and is intentionally
kept out of ``src/`` and ``tests/``. It is the single, non-duplicated seeding
helper referenced by the performance plan.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
)
from photo_composition_designer.project.services import ProjectService

#: Real fixture photos used to make decode/EXIF costs representative.
SOURCE_IMAGES = Path(__file__).resolve().parent.parent / "images"


def configure_isolated_app(tmp: Path) -> None:
    """Point the app directories at a throwaway location."""
    os.environ["PCD_DATA_DIR"] = str(tmp / "data")
    os.environ["PCD_CACHE_DIR"] = str(tmp / "cache")
    os.environ["PCD_CONFIG_DIR"] = str(tmp / "config")


def make_workspace(tmp: Path) -> WorkspaceDatabase:
    """Create an isolated workspace database under ``tmp``."""
    configure_isolated_app(tmp)
    return WorkspaceDatabase(tmp / "workspace.sqlite3")


def seed_project(
    database: WorkspaceDatabase,
    tmp: Path,
    *,
    slots: int,
    page_count: int = 1,
    gps_count: int = 0,
    quality: int = 88,
) -> tuple[int, list[int]]:
    """Create a project with ``slots`` slots per page and one photo per slot.

    Photos are re-encoded copies of real fixtures so decode cost and EXIF/GPS
    parsing are representative. ``gps_count`` photos (spread across the project)
    receive coordinates so the map path can be exercised.

    Returns:
        A ``(project_id, page_ids)`` tuple.
    """
    service = ProjectService(database)
    project = service.create_project(
        name="perf",
        page_count=page_count,
        start_date=datetime(2027, 1, 4),
        output_profile={"size": {"width": 216, "height": 154, "dpi": 300}},
    )

    source = tmp / "source"
    source.mkdir(parents=True, exist_ok=True)
    files = sorted(SOURCE_IMAGES.glob("*.jpg"))
    for index in range(min(len(files), slots)):
        with Image.open(files[index]) as image:
            image.convert("RGB").save(source / f"photo_{index:03d}.jpg", quality=quality)

    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    if gps_count:
        connection = database.connect()
        photos = PhotoRepository(connection).list(project.id)
        for index, photo in enumerate(photos[:gps_count]):
            connection.execute(
                "UPDATE photos SET gps_lat = ?, gps_lon = ? WHERE id = ?",
                (51.05 + index * 0.01, 13.74 + index * 0.01, photo.id),
            )
        connection.commit()

    with database.transaction() as connection:
        layouts = LayoutRepository(connection)
        pages = PageRepository(connection)
        assignments = AssignmentRepository(connection)
        photo_ids = [photo.id for photo in PhotoRepository(connection).list(project.id)]
        cursor = 0
        page_ids: list[int] = []
        for page in pages.list(project.id):
            page_ids.append(page.id)
            layout_slots = [
                LayoutSlot(
                    id=0,
                    layout_id=0,
                    slot_key=f"slot_{index}",
                    position=index,
                    x=index / slots,
                    y=0.0,
                    width=1.0 / slots,
                    height=1.0,
                    z_index=0,
                    crop_mode="cover",
                )
                for index in range(slots)
            ]
            layout = layouts.add(f"perf_{page.page_index}", 1, "Perf", layout_slots)
            pages.set_layout(page.id, layout.id, layout.version)
            for slot in layout.slots:
                assignments.assign(
                    project_id=project.id,
                    page_id=page.id,
                    slot_id=slot.id,
                    photo_id=photo_ids[cursor % len(photo_ids)],
                )
                cursor += 1

    return project.id, page_ids


def cleanup(tmp: Path) -> None:
    """Remove a throwaway workspace directory."""
    shutil.rmtree(tmp, ignore_errors=True)


def new_workspace(prefix: str = "pcd-perf-") -> tuple[Path, WorkspaceDatabase]:
    """Create a throwaway directory and an isolated workspace inside it."""
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    return tmp, make_workspace(tmp)
