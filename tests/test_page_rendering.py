"""Tests for full-page composition and project rendering."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.helpers import mm_to_px
from photo_composition_designer.core.output_profile import OutputProfile, SizeProfile
from photo_composition_designer.core.settings import Settings
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.layouts.loader import LayoutTemplate, SlotTemplate
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.rendering import ProjectRenderingService
from photo_composition_designer.project.repositories import (
    LayoutRepository,
    PageRepository,
)
from photo_composition_designer.project.services import ProjectService
from photo_composition_designer.render.page import PageComposer, PageRenderInput
from photo_composition_designer.render.slot_renderer import SlotAwareRenderer, SlotPhoto


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

        # The photo fills the top content region; the calendar strip is below it.
        background = (20, 20, 20)
        calendar_top = image.height - mm_to_px(3, 300) - mm_to_px(18, 300)
        strip = image.crop((0, calendar_top, image.width, image.height - mm_to_px(3, 300)))
        assert any(pixel != background for pixel in strip.getdata())
        assert (255, 0, 0) not in strip.getdata()
        red_pixel = image.getpixel((image.width // 2, mm_to_px(20, 300)))
        assert red_pixel[0] > 200 and red_pixel[1:] == (0, 0)
    finally:
        database.close()


def test_calendar_strip_stays_within_side_margins():
    profile = OutputProfile.default()
    image = PageComposer().render(
        PageRenderInput(
            page_date=date(2027, 1, 4),
            description="",
            layout=None,
            output_profile=profile,
            title_page=False,
        )
    )

    dpi = profile.size.dpi
    margin_sides = mm_to_px(profile.layout.margin_sides, dpi)
    margin_bottom = mm_to_px(profile.layout.margin_bottom, dpi)
    calendar_height = mm_to_px(profile.size.calendar_height, dpi)
    calendar_top = image.height - margin_bottom - calendar_height
    background = (20, 20, 20)

    content_x = [
        x
        for y in range(calendar_top, image.height - margin_bottom)
        for x in range(image.width)
        if image.getpixel((x, y)) != background
    ]

    assert content_x
    assert min(content_x) >= margin_sides - 8
    assert max(content_x) <= image.width - margin_sides + 2


def _is_red(pixel: tuple[int, int, int]) -> bool:
    """Return whether a pixel belongs to the red test photo."""
    return pixel[0] > 200 and pixel[1] < 60 and pixel[2] < 60


def test_description_renders_between_photo_and_calendar(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(database)
        with database.transaction() as connection:
            PageRepository(connection).update_description(page_id, "Between collage and calendar")

        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            render_input = replace(rendering.build_input(connection, page), title_page=False)
            image = PageComposer().render(render_input)

        profile = OutputProfile.default()
        dpi = profile.size.dpi
        margin_bottom = mm_to_px(profile.layout.margin_bottom, dpi)
        calendar_height = mm_to_px(profile.size.calendar_height, dpi)
        calendar_top = image.height - margin_bottom - calendar_height

        photo_bottom = max(
            y
            for y in range(calendar_top)
            for x in range(image.width)
            if _is_red(image.getpixel((x, y)))
        )
        description_y = [
            y
            for y in range(image.height)
            for x in range(image.width)
            if image.getpixel((x, y)) == (150, 150, 150)
        ]

        assert photo_bottom < calendar_top
        assert any(photo_bottom < y < calendar_top for y in description_y)
    finally:
        database.close()


def test_slot_renderer_applies_spacing_and_rounded_corners(tmp_path):
    red_path = tmp_path / "red.jpg"
    blue_path = tmp_path / "blue.jpg"
    _write_photo(red_path, (255, 0, 0))
    _write_photo(blue_path, (0, 0, 255))
    settings = Settings()
    layout = LayoutTemplate(
        key="two-up",
        version=1,
        name="Two up",
        slots=(
            SlotTemplate("left", 0.0, 0.0, 0.5, 1.0),
            SlotTemplate("right", 0.5, 0.0, 0.5, 1.0),
        ),
    )

    image = SlotAwareRenderer(settings).render(
        layout,
        {
            "left": SlotPhoto(red_path),
            "right": SlotPhoto(blue_path),
        },
        page_width=100,
        page_height=40,
        background_color=(20, 20, 20),
    )

    assert image.getpixel((50, 20)) == (20, 20, 20)
    assert image.getpixel((0, 20))[0] > 200
    assert image.getpixel((99, 20))[2] > 200
    assert image.getpixel((0, 0)) == (20, 20, 20)


def test_render_page_shows_photo_location_map(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    map_width = mm_to_px(20, 300)
    map_height = mm_to_px(20, 300)

    with database.transaction() as connection:
        connection.execute("UPDATE photos SET gps_lat = 51.05, gps_lon = 13.73")

    composer = PageComposer(
        map_renderer=lambda _coordinates: Image.new("RGB", (map_width, map_height), (0, 0, 255))
    )
    try:
        rendering = ProjectRenderingService(database, composer=composer)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            image = rendering.render_page_image(connection, page)

        map_x = image.width - mm_to_px(3, 300) - map_width // 2
        map_y = mm_to_px(6, 300) + map_height // 2
        assert image.getpixel((map_x, map_y)) == (0, 0, 255)
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


class _CountingComposer:
    """Stand-in composer that records how often a page is rendered."""

    def __init__(self) -> None:
        self.calls = 0

    def render(self, render_input) -> Image.Image:
        self.calls += 1
        return Image.new("RGB", (120, 90), "white")


def test_cached_preview_does_not_render_again(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        composer = _CountingComposer()
        rendering = ProjectRenderingService(
            database,
            composer=composer,
            preview_dir=tmp_path / "previews",
        )
        first = rendering.render_preview(project_id, page_id)
        second = rendering.render_preview(project_id, page_id)

        assert first == second
        assert composer.calls == 1, "a cached preview must not decode or render again"
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


def test_preview_invalidated_by_global_anniversaries_change(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        anniversaries_path = tmp_path / "anniversaries.ini"
        anniversaries_path.write_text("[Birthdays]\nPaul = 6.1.\n", encoding="utf-8")
        rendering = ProjectRenderingService(
            database,
            preview_dir=tmp_path / "previews",
            anniversaries_path=anniversaries_path,
        )
        first = rendering.render_preview(project_id, page_id)

        original_stat = anniversaries_path.stat()
        anniversaries_path.write_text(
            "[Birthdays]\nPaul = 7.1.\n",
            encoding="utf-8",
        )
        os.utime(
            anniversaries_path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        second = rendering.render_preview(project_id, page_id)

        assert second != first
    finally:
        database.close()
