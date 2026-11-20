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
from photo_composition_designer.render.layout_geometry import (
    compute_collage_box,
    prepare_collage,
)
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
        # Tests that are not about maps keep the page free of the default map.
        updated = page_repo.set_local_overrides(
            page.id,
            hide_local_map=True,
            hide_calendar_strip=False,
            hide_description=False,
        )
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
        background = (20, 20, 20)

        calendar_only = PageComposer().render(
            replace(
                render_input,
                description="",
                output_profile=replace(
                    profile,
                    layout=replace(profile.layout, use_photo_description=False),
                ),
            )
        )
        calendar_ink_top = min(
            y
            for y in range(calendar_top, image.height - margin_bottom)
            for x in range(image.width)
            if calendar_only.getpixel((x, y)) != background
        )

        photo_bottom = max(
            y
            for y in range(calendar_top)
            for x in range(image.width)
            if _is_red(image.getpixel((x, y)))
        )
        description_y = [
            y
            for y in range(calendar_ink_top + 2)
            for x in range(image.width)
            if image.getpixel((x, y)) == (150, 150, 150)
        ]

        assert description_y
        assert min(description_y) > photo_bottom
        assert max(description_y) <= calendar_ink_top + 1
    finally:
        database.close()


def test_description_space_is_reserved_when_text_is_empty(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(database)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            render_input = replace(rendering.build_input(connection, page), title_page=False)

        empty = PageComposer().render(render_input)
        filled = PageComposer().render(replace(render_input, description="Filled description"))

        empty_photo_bottom = max(
            y
            for y in range(empty.height)
            for x in range(empty.width)
            if _is_red(empty.getpixel((x, y)))
        )
        filled_photo_bottom = max(
            y
            for y in range(filled.height)
            for x in range(filled.width)
            if _is_red(filled.getpixel((x, y)))
        )

        assert empty_photo_bottom == filled_photo_bottom
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


def test_slot_renderer_pans_into_source_area_cropped_at_one_times_zoom(tmp_path):
    photo_path = tmp_path / "split.png"
    photo = Image.new("RGB", (200, 100), (0, 0, 255))
    photo.paste(Image.new("RGB", (100, 100), (255, 0, 0)), (0, 0))
    photo.save(photo_path)
    layout = LayoutTemplate(
        key="square",
        version=1,
        name="Square",
        slots=(SlotTemplate("main", 0.0, 0.0, 1.0, 1.0),),
    )
    renderer = SlotAwareRenderer(Settings())

    left = renderer.render(
        layout,
        {"main": SlotPhoto(photo_path, crop_focus_x=0.0)},
        page_width=100,
        page_height=100,
        background_color=(0, 0, 0),
    )
    right = renderer.render(
        layout,
        {"main": SlotPhoto(photo_path, crop_focus_x=1.0)},
        page_width=100,
        page_height=100,
        background_color=(0, 0, 0),
    )

    assert left.getpixel((50, 50))[0] > 200
    assert right.getpixel((50, 50))[2] > 200


def test_render_page_shows_photo_location_map(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    profile = OutputProfile.default()
    map_width = mm_to_px(profile.geo.map_size, 300)
    map_height = mm_to_px(profile.size.calendar_height, 300)

    with database.transaction() as connection:
        connection.execute("UPDATE photos SET gps_lat = 51.05, gps_lon = 13.73")
        connection.execute("UPDATE pages SET hide_local_map = 0 WHERE id = ?", (page_id,))

    composer = PageComposer(
        map_renderer=lambda _coordinates: Image.new("RGB", (map_width, map_height), (0, 0, 255))
    )
    try:
        rendering = ProjectRenderingService(database, composer=composer)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            render_input = replace(rendering.build_input(connection, page), title_page=False)
            image = composer.render(render_input)

        margin_sides = mm_to_px(profile.layout.margin_sides, 300)
        margin_bottom = mm_to_px(profile.layout.margin_bottom, 300)
        map_x = image.width - margin_sides - map_width
        map_y = image.height - margin_bottom - map_height // 2
        assert image.getpixel((map_x + map_width // 2, map_y)) == (0, 0, 255)
        # The calendar strip ends where the map begins.
        assert image.getpixel((map_x - 1, map_y)) != (0, 0, 255)
    finally:
        database.close()


def test_render_page_uses_empty_map_without_coordinates(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    calls: list[list[tuple[float, float]]] = []

    def renderer(coordinates: list[tuple[float, float]]):
        calls.append(coordinates)
        return Image.new("RGB", (10, 10), (0, 0, 255))

    default_profile = OutputProfile.default()
    always_profile = replace(
        default_profile,
        geo=replace(default_profile.geo, map_mode="always"),
    )
    ProjectService(database).save_project(
        project_id,
        output_profile=always_profile.to_dict(),
    )

    with database.transaction() as connection:
        connection.execute("UPDATE pages SET hide_local_map = 0 WHERE id = ?", (page_id,))

    composer = PageComposer(map_renderer=renderer)
    try:
        rendering = ProjectRenderingService(database, composer=composer)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            render_input = replace(rendering.build_input(connection, page), title_page=False)
            composer.render(render_input)

        assert calls == [[]]
    finally:
        database.close()


def test_page_local_overrides_are_passed_to_render_input(tmp_path):
    database, project_id, page_id = _setup(tmp_path)

    with database.transaction() as connection:
        PageRepository(connection).set_local_overrides(
            page_id,
            hide_local_map=True,
            hide_calendar_strip=True,
            hide_description=True,
        )

    rendering = ProjectRenderingService(database)
    with database.connect() as connection:
        page = PageRepository(connection).get(page_id)
        assert page is not None
        render_input = rendering.build_input(connection, page)

    assert render_input.hide_local_map is True
    assert render_input.hide_calendar_strip is True
    assert render_input.hide_description is True
    database.close()


def test_use_title_page_setting_controls_title_page(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    profile = OutputProfile.default()
    changed = replace(
        profile,
        calendar=replace(profile.calendar, use_title_page=False),
    )
    ProjectService(database).save_project(project_id, output_profile=changed.to_dict())

    rendering = ProjectRenderingService(database)
    with database.connect() as connection:
        page = PageRepository(connection).get(page_id)
        assert page is not None
        render_input = rendering.build_input(connection, page)

    assert render_input.title_page is False
    database.close()


def test_title_page_hides_map_by_default(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    calls: list[list[tuple[float, float]]] = []

    def renderer(coordinates: list[tuple[float, float]]):
        calls.append(coordinates)
        return Image.new("RGB", (10, 10), (0, 0, 255))

    composer = PageComposer(map_renderer=renderer)
    try:
        rendering = ProjectRenderingService(database, composer=composer)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            composer.render(rendering.build_input(connection, page))

        assert calls == []
    finally:
        database.close()


def test_page_local_map_override_hides_map(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    calls: list[list[tuple[float, float]]] = []

    def renderer(coordinates: list[tuple[float, float]]):
        calls.append(coordinates)
        return Image.new("RGB", (10, 10), (0, 0, 255))

    composer = PageComposer(map_renderer=renderer)
    try:
        rendering = ProjectRenderingService(database, composer=composer)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            render_input = replace(rendering.build_input(connection, page), title_page=False)
            composer.render(render_input)

        assert calls == []
    finally:
        database.close()


def test_auto_map_mode_hides_map_without_coordinates(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    calls: list[list[tuple[float, float]]] = []

    def renderer(coordinates: list[tuple[float, float]]):
        calls.append(coordinates)
        return Image.new("RGB", (10, 10), (0, 0, 255))

    composer = PageComposer(map_renderer=renderer)
    try:
        rendering = ProjectRenderingService(database, composer=composer)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            render_input = replace(rendering.build_input(connection, page), title_page=False)
            composer.render(render_input)

        assert calls == []
    finally:
        database.close()


def test_map_requires_visible_calendar(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    calls: list[list[tuple[float, float]]] = []

    def renderer(coordinates: list[tuple[float, float]]):
        calls.append(coordinates)
        return Image.new("RGB", (10, 10), (0, 0, 255))

    default_profile = OutputProfile.default()
    always_profile = replace(
        default_profile,
        geo=replace(default_profile.geo, map_mode="always"),
    )
    ProjectService(database).save_project(
        project_id,
        output_profile=always_profile.to_dict(),
    )

    with database.transaction() as connection:
        connection.execute(
            "UPDATE pages SET hide_local_map = 0, hide_calendar_strip = 1 WHERE id = ?",
            (page_id,),
        )

    composer = PageComposer(map_renderer=renderer)
    try:
        rendering = ProjectRenderingService(database, composer=composer)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            render_input = replace(rendering.build_input(connection, page), title_page=False)
            composer.render(render_input)

        assert calls == []
    finally:
        database.close()


def test_title_page_never_shows_map_even_without_local_override(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    calls: list[list[tuple[float, float]]] = []

    def renderer(coordinates: list[tuple[float, float]]):
        calls.append(coordinates)
        return Image.new("RGB", (10, 10), (0, 0, 255))

    default_profile = OutputProfile.default()
    always_profile = replace(
        default_profile,
        geo=replace(default_profile.geo, map_mode="always"),
    )
    ProjectService(database).save_project(
        project_id,
        output_profile=always_profile.to_dict(),
    )

    with database.transaction() as connection:
        connection.execute(
            "UPDATE pages SET hide_local_map = 0, hide_calendar_strip = 0 WHERE id = ?",
            (page_id,),
        )
        connection.execute("UPDATE photos SET gps_lat = 51.05, gps_lon = 13.73")

    composer = PageComposer(map_renderer=renderer)
    try:
        rendering = ProjectRenderingService(database, composer=composer)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            composer.render(rendering.build_input(connection, page))

        assert calls == []
    finally:
        database.close()


def test_map_spans_description_and_calendar_column():
    profile = OutputProfile.default()
    always_profile = replace(profile, geo=replace(profile.geo, map_mode="always"))
    page = _blank_page(
        output_profile=always_profile,
        description="Map column",
        hide_local_map=False,
        hide_description=False,
        title_page=False,
        hide_calendar_strip=False,
    )

    prepared = prepare_collage(
        page,
        always_profile,
        map_renderer=lambda _coordinates: Image.new("RGB", (20, 20), (0, 0, 255)),
    )

    assert prepared.map_image is not None
    assert prepared.calendar_strip is not None
    assert prepared.description_image is not None
    dpi = always_profile.size.dpi
    spacing = mm_to_px(always_profile.layout.spacing, dpi)
    map_width = mm_to_px(always_profile.geo.map_size, dpi)
    margin_sides = mm_to_px(always_profile.layout.margin_sides, dpi)
    page_width = always_profile.page_size_px()[0]
    assert prepared.map_top == prepared.box.top + prepared.box.height + spacing
    assert prepared.map_top < prepared.calendar_top
    assert prepared.calendar_strip.width == prepared.map_x
    assert prepared.description_image.width == prepared.map_x
    assert prepared.map_x + map_width == page_width - margin_sides


def test_map_uses_spacing_and_rounded_corners():
    profile = OutputProfile.default()
    map_profile = replace(profile, geo=replace(profile.geo, map_mode="always"))
    dpi = map_profile.size.dpi
    page_width, page_height = map_profile.page_size_px()
    spacing = mm_to_px(map_profile.layout.spacing, dpi)
    margin_sides = mm_to_px(map_profile.layout.margin_sides, dpi)
    margin_bottom = mm_to_px(map_profile.layout.margin_bottom, dpi)
    calendar_height = mm_to_px(map_profile.size.calendar_height, dpi)
    text_margin = mm_to_px(map_profile.layout.text_margin, dpi)
    calendar_top = page_height - margin_bottom - calendar_height
    expected_map_top = calendar_top - text_margin + spacing
    map_width = mm_to_px(map_profile.geo.map_size, dpi)
    map_height = page_height - margin_bottom - expected_map_top

    page = _blank_page(
        output_profile=map_profile,
        description="",
        hide_description=True,
        hide_local_map=False,
        hide_calendar_strip=False,
        title_page=False,
    )

    def renderer(_coordinates: list[tuple[float, float]]) -> Image.Image:
        return Image.new("RGB", (map_width, map_height), (0, 0, 255))

    prepared = prepare_collage(page, map_profile, map_renderer=renderer)

    assert prepared.map_image is not None
    assert prepared.map_top == prepared.box.top + prepared.box.height + spacing
    assert prepared.map_top == expected_map_top

    image = PageComposer(map_renderer=renderer).render(page)
    background = (20, 20, 20)
    blue = (0, 0, 255)
    map_pixels = [
        (x, y)
        for y in range(expected_map_top, page_height - margin_bottom)
        for x in range(prepared.map_x, page_width - margin_sides)
        if image.getpixel((x, y)) == blue
    ]

    assert map_pixels
    assert min(y for _, y in map_pixels) == expected_map_top
    assert max(y for _, y in map_pixels) == page_height - margin_bottom - 1
    assert min(x for x, _ in map_pixels) == prepared.map_x
    assert max(x for x, _ in map_pixels) == page_width - margin_sides - 1

    radius = min(spacing, map_width // 2, map_height // 2)
    assert image.getpixel((prepared.map_x, expected_map_top)) == background
    assert image.getpixel((prepared.map_x + radius, expected_map_top)) == blue
    assert image.getpixel((prepared.map_x, expected_map_top + radius)) == blue

    square_profile = replace(
        map_profile,
        layout=replace(map_profile.layout, use_rounded_corners=False),
    )
    square_image = PageComposer(map_renderer=renderer).render(
        replace(page, output_profile=square_profile)
    )
    assert square_image.getpixel((prepared.map_x, expected_map_top)) == blue


def test_description_alignment_default_left_and_page_center_override():
    profile = OutputProfile.default()
    base = {
        "output_profile": profile,
        "description": "A description used for alignment checks",
        "hide_local_map": True,
        "hide_description": False,
        "title_page": False,
        "hide_calendar_strip": False,
    }

    left = prepare_collage(_blank_page(**base), profile)
    centered = prepare_collage(
        _blank_page(**base, center_description=True),
        profile,
    )
    center_profile = replace(
        profile,
        layout=replace(profile.layout, description_alignment="center"),
    )
    inherited_center = prepare_collage(
        _blank_page(**{**base, "output_profile": center_profile}),
        center_profile,
    )
    forced_left = prepare_collage(
        _blank_page(**{**base, "output_profile": center_profile}, center_description=False),
        center_profile,
    )

    assert left.description_image is not None
    assert centered.description_image is not None
    assert inherited_center.description_image is not None
    assert forced_left.description_image is not None
    left_box = left.description_image.getbbox()
    center_box = centered.description_image.getbbox()
    inherited_box = inherited_center.description_image.getbbox()
    forced_box = forced_left.description_image.getbbox()
    assert left_box is not None
    assert center_box is not None
    assert inherited_box is not None
    assert forced_box is not None
    assert left_box[0] < center_box[0]
    assert inherited_box[0] > left_box[0]
    assert forced_box[0] == left_box[0]

    width = centered.description_image.width
    margin_sides = mm_to_px(profile.layout.margin_sides, profile.size.dpi)
    for box in (center_box, inherited_box):
        assert box[0] >= margin_sides - 2
        assert box[2] <= width - margin_sides + 2
        assert abs((box[0] + box[2]) / 2 - width / 2) <= 2


def test_text_margin_controls_description_gap():
    profile = OutputProfile.default()
    base = {
        "description": "A description used for spacing checks",
        "hide_local_map": True,
        "hide_description": False,
        "title_page": False,
        "hide_calendar_strip": False,
    }
    zero_profile = replace(profile, layout=replace(profile.layout, text_margin=0.0))
    wide_profile = replace(profile, layout=replace(profile.layout, text_margin=3.0))

    zero = prepare_collage(
        _blank_page(**{**base, "output_profile": zero_profile}),
        zero_profile,
    )
    wide = prepare_collage(
        _blank_page(**{**base, "output_profile": wide_profile}),
        wide_profile,
    )

    assert zero.description_top is not None
    assert wide.description_top is not None
    zero_photo_bottom = zero.box.top + zero.box.height
    wide_photo_bottom = wide.box.top + wide.box.height
    assert zero.description_top > wide.description_top
    assert zero_photo_bottom > wide_photo_bottom
    assert zero.calendar_top == wide.calendar_top


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
        default_profile = OutputProfile.default()
        changed = OutputProfile(
            size=default_profile.size,
            calendar=default_profile.calendar,
            style=replace(default_profile.style, background_color="#000000"),
            geo=default_profile.geo,
            layout=default_profile.layout,
        )
        service.save_project(project_id, output_profile=changed.to_dict())

        second = rendering.render_preview(project_id, page_id)
        assert second != first

        # A DPI change above the draft DPI does not change the rendered preview,
        # so the draft cache key stays the same. This documents the intended
        # draft-profile behaviour: the key is derived from the profile the
        # preview actually renders with, not the full-resolution profile.
        lower_dpi = OutputProfile(
            size=SizeProfile(dpi=150),
            calendar=default_profile.calendar,
            style=default_profile.style,
            geo=default_profile.geo,
            layout=default_profile.layout,
        )
        service.save_project(project_id, output_profile=lower_dpi.to_dict())
        third = rendering.render_preview(project_id, page_id)
        assert third == first
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


def test_preview_invalidated_by_changed_source_photo_bytes(tmp_path):
    """A changed source photo must invalidate the page preview (P1-W05).

    The photo bytes change but its path and GPS do not, so the only detectable
    signal is the new mtime/size recorded by the scanner. The preview key is
    revision-based, so the scan must bump the page revision.
    """
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(database, preview_dir=tmp_path / "previews")
        first = rendering.render_preview(project_id, page_id)

        # Rewrite the assigned photo with different bytes at the same path.
        source_photo = tmp_path / "source" / "p0.jpg"
        _write_photo(source_photo, (0, 255, 0))
        stat = source_photo.stat()
        os.utime(source_photo, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        from photo_composition_designer.project.repositories import SourceRootRepository

        connection = database.connect()
        root = SourceRootRepository(connection).get_active(project_id)
        assert root is not None
        InventoryService(database).scan(project_id, source_root_id=root.id)

        second = rendering.render_preview(project_id, page_id)

        assert second != first
        assert second.is_file()
    finally:
        database.close()


def _blank_page(**overrides) -> PageRenderInput:
    """Return a minimal page render input for geometry assertions."""
    defaults = {
        "page_date": date(2027, 1, 4),
        "description": "",
        "layout": None,
        "output_profile": OutputProfile.default(),
        "title_page": False,
        "hide_description": True,
    }
    defaults.update(overrides)
    return PageRenderInput(**defaults)


def _red_photo() -> Path:
    """Write a small red JPEG into a temporary file and return its path."""
    import tempfile

    path = Path(tempfile.mkdtemp()) / "red.jpg"
    Image.new("RGB", (40, 30), (255, 0, 0)).save(path)
    return path


def test_compute_collage_box_matches_renderer_content_box():
    # No description, calendar shown: the collage fills from the top margin to
    # just above the calendar strip (calendar_top - spacing).
    profile = OutputProfile.default()
    dpi = profile.size.dpi
    page_width, page_height = profile.page_size_px()
    margin_sides = mm_to_px(profile.layout.margin_sides, dpi)
    margin_top = mm_to_px(profile.layout.margin_top, dpi)
    margin_bottom = mm_to_px(profile.layout.margin_bottom, dpi)
    text_margin = mm_to_px(profile.layout.text_margin, dpi)
    calendar_height = mm_to_px(profile.size.calendar_height, dpi)

    page = _blank_page(output_profile=profile, hide_local_map=True)
    box = compute_collage_box(page, profile)

    calendar_top = page_height - margin_bottom - calendar_height
    expected_bottom = calendar_top - text_margin
    assert box.page_width == page_width
    assert box.page_height == page_height
    assert box.left == margin_sides
    assert box.top == margin_top
    assert box.width == page_width - 2 * margin_sides
    assert box.height == expected_bottom - margin_top


def test_compute_collage_box_without_calendar_uses_bottom_margin():
    profile = OutputProfile.default()
    dpi = profile.size.dpi
    page_width, page_height = profile.page_size_px()
    margin_sides = mm_to_px(profile.layout.margin_sides, dpi)
    margin_top = mm_to_px(profile.layout.margin_top, dpi)
    margin_bottom = mm_to_px(profile.layout.margin_bottom, dpi)

    page = _blank_page(
        output_profile=profile,
        hide_local_map=True,
        hide_calendar_strip=True,
    )
    box = compute_collage_box(page, profile)

    expected_bottom = page_height - margin_bottom
    assert box.top == margin_top
    assert box.left == margin_sides
    assert box.height == expected_bottom - margin_top


def test_compute_collage_box_leaves_room_for_description():
    # A visible description sits below the collage and above the calendar, so
    # the collage box must end above the description's top edge.
    profile = OutputProfile.default()
    dpi = profile.size.dpi
    page_height = profile.page_size_px()[1]
    margin_bottom = mm_to_px(profile.layout.margin_bottom, dpi)
    calendar_height = mm_to_px(profile.size.calendar_height, dpi)
    calendar_top = page_height - margin_bottom - calendar_height

    page = _blank_page(
        output_profile=profile,
        hide_local_map=True,
        hide_description=False,
        description="A caption under the photos",
    )
    prepared = prepare_collage(page, profile)
    box = prepared.box

    assert prepared.description_image is not None
    assert prepared.description_top is not None
    # The collage ends at or above where the description begins.
    assert box.top + box.height <= prepared.description_top
    # The description stays above the calendar strip.
    assert prepared.description_top < calendar_top


def test_title_page_description_matches_calendar_spacing():
    # The title strip has no day names, so its first ink sits lower than a
    # calendar's. The description must keep the same distance from the page
    # bottom as on a page with a calendar instead of sinking towards the title.
    profile = OutputProfile.default()
    shared = {
        "output_profile": profile,
        "hide_local_map": True,
        "hide_description": False,
        "description": "A caption under the photos",
    }
    calendar_prepared = prepare_collage(_blank_page(**shared), profile)
    title_prepared = prepare_collage(
        _blank_page(
            **shared,
            title_page=True,
            title="This is the title of the composition",
        ),
        profile,
    )

    assert calendar_prepared.description_top is not None
    assert title_prepared.description_top is not None
    assert title_prepared.description_top == calendar_prepared.description_top


def test_compute_collage_box_matches_composer_paste_position():
    # The collage the composer renders must land exactly at the computed box.
    profile = OutputProfile.default()
    layout = LayoutTemplate(
        key="one",
        version=1,
        name="One",
        slots=(SlotTemplate("main", 0.0, 0.0, 1.0, 1.0),),
    )
    page = _blank_page(
        output_profile=profile,
        layout=layout,
        hide_local_map=True,
        description="",
    )
    box = compute_collage_box(page, profile)

    red_path = _red_photo()
    rendered = PageComposer().render(replace(page, assigned_photos={"main": SlotPhoto(red_path)}))
    # Sample the centre of the collage box; the photo fills it.
    red, green, blue = rendered.getpixel((box.left + box.width // 2, box.top + box.height // 2))
    assert red > 200 and green < 60 and blue < 60


def test_slot_overlay_rectangles_match_collage_box():
    from photo_composition_designer.project.models import LayoutSlot
    from photo_composition_designer.render.layout_geometry import slot_overlay_rectangles

    box = compute_collage_box(_blank_page(hide_local_map=True), OutputProfile.default())
    slots = [
        LayoutSlot(
            id=1,
            layout_id=1,
            slot_key="left",
            position=0,
            x=0.0,
            y=0.0,
            width=0.5,
            height=1.0,
            z_index=0,
            crop_mode="cover",
        ),
        LayoutSlot(
            id=2,
            layout_id=1,
            slot_key="right",
            position=1,
            x=0.5,
            y=0.0,
            width=0.5,
            height=1.0,
            z_index=0,
            crop_mode="cover",
        ),
    ]

    rects = slot_overlay_rectangles(slots, box)

    left, right = rects
    # Both slots together span the full collage box width, expressed as
    # percentages of the full page.
    assert left.left == (box.left / box.page_width) * 100.0
    assert right.left == ((box.left + 0.5 * box.width) / box.page_width) * 100.0
    assert left.width == (0.5 * box.width / box.page_width) * 100.0
    assert left.top == (box.top / box.page_height) * 100.0
    assert left.height == (box.height / box.page_height) * 100.0
    # Adjacent slots share an edge exactly.
    assert left.left + left.width == right.left
