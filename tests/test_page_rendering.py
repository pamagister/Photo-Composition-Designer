"""Tests for full-page composition and project rendering."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.helpers import mm_to_px
from photo_composition_designer.core.output_profile import OutputProfile, SizeProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.rendering import ProjectRenderingService
from photo_composition_designer.project.repositories import (
    LayoutRepository,
    PageRepository,
)
from photo_composition_designer.project.services import ProjectService


def _write_photo(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _setup(tmp_path: Path) -> tuple[WorkspaceDatabase, int, int]:
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    service = ProjectService(database)
    project = service.create_project(
        name="Render",
        page_count=1,
        start_date=datetime(2027, 1, 4),
    )

    source = tmp_path / "source"
    _write_photo(source / "p0.jpg", (255, 0, 0))
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    with database.transaction() as connection:
        layout_repo = LayoutRepository(connection)
        page_repo = PageRepository(connection)
        page = page_repo.list(project.id)[0]
        slots = [
            LayoutSlot(
                id=0,
                layout_id=0,
                slot_key="main",
                position=0,
                x=0.0,
                y=0.0,
                width=1.0,
                height=1.0,
                z_index=0,
                crop_mode="cover",
            )
        ]
        layout = layout_repo.add("single_full", 1, "Single", slots)
        page_repo.set_layout(page.id, layout.id, layout.version)
        updated = page_repo.get(page.id)
        assert updated is not None
        page_id = updated.id

    photo_id = database.connect().execute("SELECT id FROM photos").fetchone()["id"]
    from photo_composition_designer.project.repositories import AssignmentRepository

    with database.transaction() as connection:
        AssignmentRepository(connection).assign(
            project_id=project.id,
            page_id=page_id,
            slot_id=layout.slots[0].id,
            photo_id=photo_id,
        )
    return database, project.id, page_id


def test_render_page_uses_profile_page_size(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(database)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            profile = rendering.profile_for(connection, project_id)
            image = rendering.render_page_image(connection, page)

        assert image.size == profile.page_size_px()
        assert image.size == (
            mm_to_px(profile.size.width, profile.size.dpi),
            mm_to_px(profile.size.height, profile.size.dpi),
        )
    finally:
        database.close()


def test_render_page_contains_photo_and_calendar(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(database)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            image = rendering.render_page_image(connection, page)

        red, green, blue = image.getpixel((image.width // 2, image.height // 2))
        assert red > 200 and green < 60 and blue < 60

        # The calendar strip is rendered at the top of the page and contains
        # non-background pixels even though its background matches the page.
        background = (20, 20, 20)
        strip = image.crop((0, 0, image.width, mm_to_px(18, 300)))
        assert any(pixel != background for pixel in strip.getdata())
    finally:
        database.close()


def test_render_page_honours_custom_profile_size(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        service = ProjectService(database)
        profile = OutputProfile.from_dict(
            {
                "size": {
                    "width": 100,
                    "height": 80,
                    "calendar_height": 0,
                    "dpi": 100,
                }
            }
        )
        service.save_project(project_id, output_profile=profile.to_dict())

        rendering = ProjectRenderingService(database)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            image = rendering.render_page_image(connection, page)

        assert image.size == (mm_to_px(100, 100), mm_to_px(80, 100))
    finally:
        database.close()


def test_preview_is_cached_and_invalidated_by_revision(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(database, preview_dir=tmp_path / "previews")
        first = rendering.render_preview(project_id, page_id)
        second = rendering.render_preview(project_id, page_id)
        assert first == second
        assert first.is_file()

        with database.transaction() as connection:
            PageRepository(connection).update_description(page_id, "A new description")
        third = rendering.render_preview(project_id, page_id)

        assert third != first
        assert third.is_file()
    finally:
        database.close()


def test_preview_invalidated_by_profile_change(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(database, preview_dir=tmp_path / "previews")
        first = rendering.render_preview(project_id, page_id)

        service = ProjectService(database)
        changed = OutputProfile(
            size=SizeProfile(dpi=150),
            calendar=OutputProfile.default().calendar,
            style=OutputProfile.default().style,
            geo=OutputProfile.default().geo,
            layout=OutputProfile.default().layout,
        )
        service.save_project(project_id, output_profile=changed.to_dict())

        second = rendering.render_preview(project_id, page_id)
        assert second != first
    finally:
        database.close()
