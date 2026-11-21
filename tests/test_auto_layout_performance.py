"""Performance coverage for project-sized automatic collage pages.

The test is marked slow and excluded from the default ``make test`` run. It
builds a full 53-page project with automatic layouts and renders every page
preview, recording the total and per-page timings.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.layouts.auto_layout import AutoPhoto, build_auto_layout
from photo_composition_designer.layouts.loader import AUTO_LAYOUT_KEY, AUTO_LAYOUT_NAME
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.rendering import (
    ProjectRenderingService,
    collage_aspect_for_page,
)
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
)
from photo_composition_designer.project.services import ProjectService

pytestmark = pytest.mark.slow

#: A full calendar year of weekly pages.
PAGE_COUNT = 53

#: Photos per automatic page; a realistic upper bound for a collage page.
PHOTOS_PER_PAGE = 30

#: Generous wall-clock budget for rendering every page preview.
TOTAL_BUDGET_SECONDS = 120.0


def _write_photo(path: Path, index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    colour = ((index * 37) % 255, (index * 71) % 255, (index * 113) % 255)
    Image.new("RGB", (640, 480), colour).save(path)


def _setup_project(tmp_path: Path) -> tuple[WorkspaceDatabase, int, int, int]:
    """Create a 53-page project with a shared automatic layout."""
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    profile = OutputProfile.default()
    profile = OutputProfile.from_dict(
        {
            **profile.to_dict(),
            "size": {**profile.size.to_dict(), "width": 100, "height": 80, "dpi": 72},
        }
    )
    project = ProjectService(database).create_project(
        name="Auto performance",
        page_count=PAGE_COUNT,
        start_date=datetime(2027, 1, 4),
        output_profile=profile.to_dict(),
    )
    source = tmp_path / "source"
    for index in range(PHOTOS_PER_PAGE):
        _write_photo(source / f"photo_{index:02d}.jpg", index)
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    with database.connect() as connection:
        pages = PageRepository(connection).list(project.id)
        aspect = collage_aspect_for_page(pages[0], profile)
        photo_ids = [row["id"] for row in connection.execute("SELECT id FROM photos ORDER BY id")]
    engine_photos = tuple(
        AutoPhoto(key=str(index), width=640, height=480) for index in range(PHOTOS_PER_PAGE)
    )
    slots = build_auto_layout(engine_photos, aspect)

    with database.transaction() as connection:
        layout_repo = LayoutRepository(connection)
        page_repo = PageRepository(connection)
        slot_rows = [
            LayoutSlot(
                id=0,
                layout_id=0,
                slot_key=slot.key,
                position=index,
                x=slot.x,
                y=slot.y,
                width=slot.width,
                height=slot.height,
                z_index=0,
                crop_mode="cover",
            )
            for index, slot in enumerate(slots)
        ]
        layout = layout_repo.add(AUTO_LAYOUT_KEY, 1, AUTO_LAYOUT_NAME, slot_rows)
        assignments = AssignmentRepository(connection)
        for page in page_repo.list(project.id):
            page_repo.set_layout(page.id, layout.id, layout.version)
            for slot, photo_id in zip(layout.slots, photo_ids, strict=True):
                assignments.assign(
                    project_id=project.id,
                    page_id=page.id,
                    slot_id=slot.id,
                    photo_id=photo_id,
                )
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
    return database, project.id, page.id, len(slots)


def test_project_sized_auto_layout_previews_fit_budget(tmp_path: Path) -> None:
    database, project_id, _first_page_id, slot_count = _setup_project(tmp_path)
    try:
        assert slot_count == PHOTOS_PER_PAGE
        preview_dir = tmp_path / "previews"
        rendering = ProjectRenderingService(database, preview_dir=preview_dir)

        started = time.perf_counter()
        timings: list[float] = []
        with database.connect() as connection:
            page_ids = [page.id for page in PageRepository(connection).list(project_id)]
        for page_id in page_ids:
            page_started = time.perf_counter()
            path = rendering.render_preview(project_id, page_id, max_width=320)
            timings.append(time.perf_counter() - page_started)
            assert path.is_file()
        elapsed = time.perf_counter() - started

        print(
            f"auto-layout preview: {len(page_ids)} pages, {elapsed:.2f}s total, "
            f"max page {max(timings):.2f}s, mean {sum(timings) / len(timings):.3f}s"
        )
        assert elapsed < TOTAL_BUDGET_SECONDS
    finally:
        database.close()
