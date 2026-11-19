"""Correctness tests for the preview performance work (plan Phase 0).

These tests guard the *contracts* the performance phases rely on, not timing:

* the preview cache key changes for every render input and hits when unchanged;
* a draft preview (reduced DPI) stays visually close to the full preview at 320
  and 640 px across representative geometries;
* the full-resolution export path is unaffected by preview-only changes.

They are intentionally free of wall-clock assertions so they stay deterministic.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.rendering import (
    ProjectRenderingService,
    write_preview,
)
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
)
from photo_composition_designer.project.services import ProjectService
from photo_composition_designer.render.page import PageComposer


def _write_photo(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), color).save(path)


def _setup(
    tmp_path: Path,
    *,
    slots: int = 1,
    columns: int = 1,
    hide_local_map: bool = True,
    profile: OutputProfile | None = None,
) -> tuple[WorkspaceDatabase, int, int]:
    """Create a one-page project with ``slots`` photos in a grid of ``columns``."""
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    service = ProjectService(database)
    project = service.create_project(
        name="Perf",
        page_count=1,
        start_date=datetime(2027, 1, 4),
        output_profile=(profile or OutputProfile.default()).to_dict(),
    )

    source = tmp_path / "source"
    for index in range(slots):
        _write_photo(source / f"p{index}.jpg", (index * 20 % 255, 40, 200))
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    rows = max(1, (slots + columns - 1) // columns)
    with database.transaction() as connection:
        layout_repo = LayoutRepository(connection)
        page_repo = PageRepository(connection)
        page = page_repo.list(project.id)[0]
        layout_slots = [
            LayoutSlot(
                id=0,
                layout_id=0,
                slot_key=f"slot_{index}",
                position=index,
                x=(index % columns) / columns,
                y=(index // columns) / rows,
                width=1.0 / columns,
                height=1.0 / rows,
                z_index=0,
                crop_mode="cover",
            )
            for index in range(slots)
        ]
        layout = layout_repo.add("perf", 1, "Perf", layout_slots)
        page_repo.set_layout(page.id, layout.id, layout.version)
        updated = page_repo.set_local_overrides(
            page.id,
            hide_local_map=hide_local_map,
            hide_calendar_strip=False,
            hide_description=False,
        )
        assert updated is not None
        page_id = updated.id

    photo_ids = [
        row["id"] for row in database.connect().execute("SELECT id FROM photos").fetchall()
    ]
    with database.transaction() as connection:
        assignments = AssignmentRepository(connection)
        for index, slot in enumerate(layout.slots):
            assignments.assign(
                project_id=project.id,
                page_id=page_id,
                slot_id=slot.id,
                photo_id=photo_ids[index % len(photo_ids)],
            )
    return database, project.id, page_id


def _downscaled(image: Image.Image, width: int) -> Image.Image:
    height = max(1, round(image.height * width / image.width))
    return image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------
# Preview cache-key behaviour
# ---------------------------------------------------------------------------


def test_preview_cache_key_changes_for_every_render_input(tmp_path):
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(database, preview_dir=tmp_path / "previews")
        connection = database.connect()
        page = PageRepository(connection).get(page_id)
        assert page is not None
        profile = rendering.profile_for(connection, project_id)

        baseline = rendering.preview_cache_key(page, profile, max_width=640, mode="preview")

        # max_width changes the key.
        assert rendering.preview_cache_key(page, profile, max_width=320, mode="preview") != baseline
        # mode changes the key.
        assert rendering.preview_cache_key(page, profile, max_width=640, mode="other") != baseline
        # profile change changes the key.
        changed_profile = replace(profile, size=replace(profile.size, dpi=150))
        assert (
            rendering.preview_cache_key(page, changed_profile, max_width=640, mode="preview")
            != baseline
        )
        # revision change changes the key.
        revised = replace(page, render_revision=page.render_revision + 1)
        assert (
            rendering.preview_cache_key(revised, profile, max_width=640, mode="preview") != baseline
        )
        # identical inputs hit.
        assert rendering.preview_cache_key(page, profile, max_width=640, mode="preview") == baseline
    finally:
        database.close()


def test_preview_cache_key_covers_layout_and_anniversaries(tmp_path):
    anniversaries_path = tmp_path / "anniversaries.ini"
    anniversaries_path.write_text("[Birthdays]\nPaul = 6.1.\n", encoding="utf-8")
    database, project_id, page_id = _setup(tmp_path)
    try:
        rendering = ProjectRenderingService(
            database,
            preview_dir=tmp_path / "previews",
            anniversaries_path=anniversaries_path,
        )
        connection = database.connect()
        page = PageRepository(connection).get(page_id)
        assert page is not None
        profile = rendering.profile_for(connection, project_id)

        baseline = rendering.preview_cache_key(page, profile, max_width=640, mode="preview")

        # A different layout id/version changes the key.
        relayout = replace(page, layout_id=page.layout_id, layout_version=page.layout_version + 1)
        assert (
            rendering.preview_cache_key(relayout, profile, max_width=640, mode="preview")
            != baseline
        )

        # Changing the anniversaries file changes the key.
        original_stat = anniversaries_path.stat()
        anniversaries_path.write_text("[Birthdays]\nPaul = 7.1.\n", encoding="utf-8")
        import os

        os.utime(anniversaries_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        assert rendering.preview_cache_key(page, profile, max_width=640, mode="preview") != baseline
    finally:
        database.close()


# ---------------------------------------------------------------------------
# Draft-preview closeness (guards D1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width", [320, 640])
@pytest.mark.parametrize("slots,columns", [(1, 1), (6, 3), (12, 4)])
def test_draft_preview_is_visually_close_to_full_preview(tmp_path, width, slots, columns):
    database, project_id, page_id = _setup(tmp_path, slots=slots, columns=columns)
    try:
        rendering = ProjectRenderingService(database, preview_dir=tmp_path / "previews")
        connection = database.connect()
        page = PageRepository(connection).get(page_id)
        assert page is not None
        profile = rendering.profile_for(connection, project_id)

        render_input = rendering.build_input(connection, page)
        composer = PageComposer()

        full = composer.render(render_input)
        full_path = tmp_path / "cache" / "full.jpg"
        write_preview(full, full_path, max_width=width)
        full_preview = np.asarray(Image.open(full_path).convert("RGB"), dtype=int)

        # Draft profile: reduce only the DPI so the working resolution drops.
        draft_profile = replace(profile, size=replace(profile.size, dpi=150))
        draft_input = replace(render_input, output_profile=draft_profile)
        draft = composer.render(draft_input)
        draft_path = tmp_path / "cache" / "draft.jpg"
        write_preview(draft, draft_path, max_width=width)
        draft_preview = np.asarray(Image.open(draft_path).convert("RGB"), dtype=int)

        difference = np.abs(full_preview - draft_preview)
        # A draft render is a preview approximation, not a pixel match. It must
        # stay close: mean absolute error below 12/255 and 99th percentile below
        # 60/255 across representative solid-colour slot layouts.
        assert difference.mean() < 12.0
        assert np.percentile(difference, 99) < 60.0
    finally:
        database.close()


# ---------------------------------------------------------------------------
# Export parity (guards "no silent quality loss in exports")
# ---------------------------------------------------------------------------


def test_full_resolution_export_is_not_affected_by_preview(tmp_path):
    """The full-resolution page render must ignore preview-only settings.

    The exporter calls ``render_page_image``; a preview-only draft must never
    change its pixel output. We render the full page, write a preview, and prove
    the full render is stable and at the profile's full resolution.
    """
    database, project_id, page_id = _setup(tmp_path, slots=3, columns=3)
    try:
        rendering = ProjectRenderingService(database, preview_dir=tmp_path / "previews")
        connection = database.connect()
        page = PageRepository(connection).get(page_id)
        assert page is not None
        profile = rendering.profile_for(connection, project_id)

        first = rendering.render_page_image(connection, page)
        second = rendering.render_page_image(connection, page)

        assert first.size == profile.page_size_px()
        assert first.size == second.size
        # Full renders are deterministic for identical inputs.
        assert np.array_equal(np.asarray(first), np.asarray(second))

        # Writing a preview must not alter the full-resolution output.
        write_preview(first, tmp_path / "cache" / "p.jpg", max_width=320)
        third = rendering.render_page_image(connection, page)
        assert third.size == profile.page_size_px()
        assert np.array_equal(np.asarray(first), np.asarray(third))
    finally:
        database.close()


def test_draft_profile_only_scales_dpi(tmp_path):
    """A draft profile must change only ``size.dpi`` (D1)."""
    profile = OutputProfile.default()
    draft = replace(profile, size=replace(profile.size, dpi=150))
    assert draft.size.dpi == 150
    assert draft.size.width == profile.size.width
    assert draft.size.height == profile.size.height
    assert draft.calendar == profile.calendar
    assert draft.style == profile.style
    assert draft.geo == profile.geo
    assert draft.layout == profile.layout
    assert draft.profile_hash() != profile.profile_hash()


def test_draft_profile_derivation_covers_preview_width():
    """``draft_profile`` scales only ``size.dpi`` to cover ``max_width`` at 1.5x."""
    from photo_composition_designer.project.rendering import draft_dpi, draft_profile

    profile = OutputProfile.default()  # 216x154 mm @ 300 dpi
    for max_width in (320, 640):
        draft = draft_profile(profile, max_width)
        # Only DPI changes.
        assert draft.size.width == profile.size.width
        assert draft.size.height == profile.size.height
        assert draft.size.calendar_height == profile.size.calendar_height
        assert draft.calendar == profile.calendar
        assert draft.style == profile.style
        assert draft.geo == profile.geo
        assert draft.layout == profile.layout
        # The draft DPI is capped at the full DPI and covers the preview width.
        assert draft.size.dpi <= profile.size.dpi
        rendered_width = round(profile.size.width * draft.size.dpi / 25.4)
        assert rendered_width >= max_width
        # The key distinguishes draft from full renders.
        assert draft.profile_hash() != profile.profile_hash()

    # A wider preview needs a higher DPI (up to the cap).
    assert draft_dpi(profile, 640) >= draft_dpi(profile, 320)
    # A very wide preview never exceeds the full DPI.
    assert draft_dpi(profile, 10_000) == profile.size.dpi


# ---------------------------------------------------------------------------
# build_input batches its lookups (D7)
# ---------------------------------------------------------------------------


def _count_queries(database, project_id: int, page_id: int) -> int:
    """Return how many SQL statements ``build_input`` issues for one page."""
    rendering = ProjectRenderingService(database)
    connection = database.connect()
    page = PageRepository(connection).get(page_id)
    assert page is not None

    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    try:
        rendering.build_input(connection, page)
    finally:
        connection.set_trace_callback(None)
    # The trace callback also fires for the trailing COMMIT issued by sqlite3;
    # count only SELECT statements issued by build_input.
    return sum(1 for statement in statements if statement.lstrip().upper().startswith("SELECT"))


def test_build_input_query_count_is_constant(tmp_path):
    """build_input must not issue per-assignment queries (D7)."""
    database, project_id, page_id = _setup(tmp_path / "few", slots=8, columns=4)
    try:
        few = _count_queries(database, project_id, page_id)
    finally:
        database.close()

    database2, project_id2, page_id2 = _setup(tmp_path / "many", slots=40, columns=8)
    try:
        many = _count_queries(database2, project_id2, page_id2)
    finally:
        database2.close()

    # The query count must not grow with the number of slots.
    assert many == few
    # Sanity: it is a small constant, not a per-slot N+1 (45 slots would be ~90).
    assert many <= 6


# ---------------------------------------------------------------------------
# Map render cache (P3-W04)
# ---------------------------------------------------------------------------


def test_map_cache_key_changes_with_coordinates():
    """A coordinate change produces a new map cache key."""
    from photo_composition_designer.render.layout_geometry import _map_cache_key

    profile = OutputProfile.default()
    key1 = _map_cache_key(profile, 200, 150, [(48.1, 11.5), (48.2, 11.6)])
    key2 = _map_cache_key(profile, 200, 150, [(48.1, 11.5), (48.3, 11.7)])
    assert key1 != key2

    # Same coordinates in a different order produce the same key.
    key3 = _map_cache_key(profile, 200, 150, [(48.2, 11.6), (48.1, 11.5)])
    assert key1 == key3

    # A profile change produces a new key.
    changed = replace(profile, style=replace(profile.style, background_color="#000000"))
    key4 = _map_cache_key(changed, 200, 150, [(48.1, 11.5), (48.2, 11.6)])
    assert key1 != key4

    # A dimension change produces a new key.
    key5 = _map_cache_key(profile, 300, 150, [(48.1, 11.5), (48.2, 11.6)])
    assert key1 != key5


def test_map_cache_hit_on_repeat(tmp_path):
    """A repeat render with the same coordinates is a cache hit."""
    from photo_composition_designer.render.layout_geometry import (
        _map_cache,
        clear_map_cache,
    )

    clear_map_cache()
    profile = OutputProfile.default()
    coords = [(48.1, 11.5), (48.2, 11.6)]

    from photo_composition_designer.core.anniversaries import Anniversaries
    from photo_composition_designer.render.layout_geometry import _render_map
    from photo_composition_designer.render.page import PageRenderInput

    page = PageRenderInput(
        page_date=date(2027, 1, 4),
        description="",
        layout=None,
        output_profile=profile,
        gps_coordinates=tuple(coords),
        anniversaries=Anniversaries(None),
    )

    # First render populates the cache.
    _render_map(page, profile, 200, 150, None)
    assert len(_map_cache) == 1

    # Second render is a cache hit (cache size unchanged, no new entry).
    _render_map(page, profile, 200, 150, None)
    assert len(_map_cache) == 1

    # A different coordinate set produces a new entry.
    page2 = replace(page, gps_coordinates=((48.3, 11.7),))
    _render_map(page2, profile, 200, 150, None)
    assert len(_map_cache) == 2


def test_map_cache_bounded(tmp_path):
    """The map cache evicts the least-recently-used entry when full."""
    from photo_composition_designer.core.anniversaries import Anniversaries
    from photo_composition_designer.render.layout_geometry import (
        _MAP_CACHE_SIZE,
        _map_cache,
        _render_map,
        clear_map_cache,
    )
    from photo_composition_designer.render.page import PageRenderInput

    clear_map_cache()
    profile = OutputProfile.default()
    anniversaries = Anniversaries(None)

    # Fill the cache beyond its capacity with distinct coordinate sets.
    for index in range(_MAP_CACHE_SIZE + 5):
        page = PageRenderInput(
            page_date=date(2027, 1, 4),
            description="",
            layout=None,
            output_profile=profile,
            gps_coordinates=((48.0 + index * 0.1, 11.0),),
            anniversaries=anniversaries,
        )
        _render_map(page, profile, 200, 150, None)

    # The cache must not exceed its cap.
    assert len(_map_cache) <= _MAP_CACHE_SIZE
