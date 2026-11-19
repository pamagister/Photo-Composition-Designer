"""Tests for page editing: layout changes, crops, descriptions and previews."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from starlette.testclient import TestClient

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
)
from photo_composition_designer.project.services import ProjectService


@pytest.fixture()
def editor_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    return TestClient(create_app(GuiSettings()))


def _write_photo(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _seed(
    tmp_path: Path,
    *,
    photo_count: int = 4,
    layout_key: str = "four_quadrants",
) -> tuple[WorkspaceDatabase, PageEditingService, int, int, list[int], list[int]]:
    """Create a one-page project with a persisted catalogue layout snapshot."""
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    project = ProjectService(database).create_project(
        name="Editing",
        page_count=1,
        start_date=datetime(2027, 1, 4),
    )

    source = tmp_path / "source"
    for index in range(photo_count):
        _write_photo(source / f"photo_{index:02d}.jpg", (index * 50, 0, 0))
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]

    editing = PageEditingService(database)
    editing.change_layout(project.id, page.id, layout_key)

    with database.connect() as connection:
        page = PageRepository(connection).get(page.id)
        assert page is not None and page.layout_id is not None
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        assert layout is not None
        photo_ids = [
            row["id"] for row in connection.execute("SELECT id FROM photos ORDER BY id").fetchall()
        ]
        slot_ids = [slot.id for slot in layout.slots]

    return database, editing, project.id, page.id, photo_ids, slot_ids


def _assign_all(
    editing: PageEditingService,
    project_id: int,
    page_id: int,
    photo_ids: list[int],
    slot_ids: list[int],
) -> None:
    for photo_id, slot_id in zip(photo_ids, slot_ids, strict=True):
        editing.assign_to_empty_slot(project_id, page_id, slot_id, photo_id)


def _page_revision(database: WorkspaceDatabase, page_id: int) -> int:
    with database.connect() as connection:
        page = PageRepository(connection).get(page_id)
        assert page is not None
        return page.render_revision


def _stored_revision(page_id: int) -> int:
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        return _page_revision(database, page_id)
    finally:
        database.close()


def test_change_layout_preview_is_deterministic_and_reports_displaced(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        _assign_all(editing, project_id, page_id, photo_ids, slot_ids)

        preview = editing.plan_layout_change(project_id, page_id, "two_columns")
        repeated = editing.plan_layout_change(project_id, page_id, "two_columns")

        assert preview == repeated
        assert preview.layout_key == "two_columns"
        assert preview.slot_count == 2
        assert len(preview.preserved) == 2
        assert {photo.id for photo in preview.displaced} == {
            photo_ids[2],
            photo_ids[3],
        }
        assert preview.has_displaced

        # Previewing never mutates assignments.
        with database.connect() as connection:
            assert len(AssignmentRepository(connection).list_by_page(page_id)) == 4
    finally:
        database.close()


def test_change_layout_applies_mapping_and_returns_displaced_to_pool(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        _assign_all(editing, project_id, page_id, photo_ids, slot_ids)
        before_revision = _page_revision(database, page_id)

        result = editing.change_layout(project_id, page_id, "two_columns")

        assert result.layout_key == "two_columns"
        assert len(result.preserved) == 2
        assert _page_revision(database, page_id) > before_revision

        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None and layout.key == "two_columns"
            assert len(layout.slots) == 2

            assignments = AssignmentRepository(connection).list_by_page(page_id)
            assert {assignment.photo_id for assignment in assignments} == {
                photo_ids[0],
                photo_ids[1],
            }
            assert {assignment.slot_id for assignment in assignments} == {
                slot.id for slot in layout.slots
            }

        unused_ids = {photo.id for photo in editing.unused_pool(project_id)}
        assert unused_ids == {photo_ids[2], photo_ids[3]}
    finally:
        database.close()


def test_change_layout_preserves_crop_settings(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        editing.assign_to_empty_slot(project_id, page_id, slot_ids[0], photo_ids[0])
        editing.set_crop(
            project_id,
            page_id,
            slot_ids[0],
            crop_zoom=1.8,
            crop_focus_x=0.25,
            crop_focus_y=0.75,
        )

        editing.change_layout(project_id, page_id, "two_columns")

        with database.connect() as connection:
            assignments = AssignmentRepository(connection).list_by_page(page_id)
            assert len(assignments) == 1
            assignment = assignments[0]
            assert assignment.photo_id == photo_ids[0]
            assert assignment.crop_zoom == pytest.approx(1.8)
            assert assignment.crop_focus_x == pytest.approx(0.25)
            assert assignment.crop_focus_y == pytest.approx(0.75)
    finally:
        database.close()


def test_change_layout_rejects_unknown_layout_without_side_effects(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        _assign_all(editing, project_id, page_id, photo_ids, slot_ids)
        before_revision = _page_revision(database, page_id)

        with pytest.raises(ProjectError):
            editing.change_layout(project_id, page_id, "does_not_exist")

        assert _page_revision(database, page_id) == before_revision
        with database.connect() as connection:
            assignments = AssignmentRepository(connection).list_by_page(page_id)
            assert {assignment.photo_id for assignment in assignments} == set(photo_ids)
    finally:
        database.close()


def test_set_crop_persists_values_and_increments_revision(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        editing.assign_to_empty_slot(project_id, page_id, slot_ids[0], photo_ids[0])
        before_revision = _page_revision(database, page_id)

        editing.set_crop(
            project_id,
            page_id,
            slot_ids[0],
            crop_zoom=2.5,
            crop_focus_x=0.1,
            crop_focus_y=0.9,
        )

        with database.connect() as connection:
            assignment = AssignmentRepository(connection).list_by_page(page_id)[0]
        assert assignment.crop_zoom == pytest.approx(2.5)
        assert assignment.crop_focus_x == pytest.approx(0.1)
        assert assignment.crop_focus_y == pytest.approx(0.9)
        assert _page_revision(database, page_id) == before_revision + 1
    finally:
        database.close()


def test_set_crop_rejects_invalid_values_without_side_effects(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        editing.assign_to_empty_slot(project_id, page_id, slot_ids[0], photo_ids[0])
        before_revision = _page_revision(database, page_id)

        with pytest.raises(ProjectError):
            editing.set_crop(project_id, page_id, slot_ids[0], crop_zoom=0.5)
        with pytest.raises(ProjectError):
            editing.set_crop(project_id, page_id, slot_ids[0], crop_focus_x=1.5)

        with database.connect() as connection:
            assignment = AssignmentRepository(connection).list_by_page(page_id)[0]
        assert assignment.crop_zoom == pytest.approx(1.0)
        assert assignment.crop_focus_x == pytest.approx(0.5)
        assert _page_revision(database, page_id) == before_revision
    finally:
        database.close()


def test_set_description_persists_text_and_increments_revision(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        before_revision = _page_revision(database, page_id)

        editing.set_description(project_id, page_id, "A calm week by the lake.")

        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
        assert page is not None
        assert page.description == "A calm week by the lake."
        assert page.render_revision == before_revision + 1
    finally:
        database.close()


def test_layout_preview_route_lists_displaced_photos(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_via_client(tmp_path)
    response = editor_client.get(
        f"/projects/{project_id}/pages/{page_id}/layout/preview",
        params={"layout_key": "two_columns"},
    )

    assert response.status_code == 200
    assert "will return to the unused pool" in response.text
    assert "photo_02.jpg" in response.text
    assert "photo_03.jpg" in response.text


def test_layout_apply_requires_confirmation_when_photos_are_displaced(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_via_client(tmp_path)
    before = _stored_revision(page_id)

    blocked = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "two_columns"},
    )
    assert blocked.status_code == 200
    assert "will return to the unused pool" in blocked.text
    assert blocked.headers["HX-Retarget"] == "#layout-change-preview"
    assert blocked.headers["HX-Reswap"] == "innerHTML"
    assert _stored_revision(page_id) == before

    applied = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "two_columns", "confirm": "1"},
    )
    assert applied.status_code == 200
    assert "Layout changed." in applied.text
    assert f'data-render-revision="{before + 1}"' in applied.text
    assert applied.headers["HX-Trigger"] == "pcd:refresh-unused"


def test_crop_route_persists_values(editor_client, tmp_path):
    project_id, page_id, _, slot_ids = _seed_via_client(tmp_path, photo_count=1, slots=1)

    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/crop",
        data={
            "slot_id": slot_ids[0],
            "crop_zoom": "2.0",
            "crop_focus_x": "0.25",
            "crop_focus_y": "0.8",
        },
    )

    assert response.status_code == 200
    assert "Crop updated." in response.text
    assert response.headers["HX-Trigger"] == "pcd:refresh-unused"
    assert f'id="page-thumb-preview-{page_id}"' in response.text
    assert 'hx-swap-oob="outerHTML"' in response.text

    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            assignment = AssignmentRepository(connection).list_by_page(page_id)[0]
    finally:
        database.close()
    assert assignment.crop_zoom == pytest.approx(2.0)
    assert assignment.crop_focus_x == pytest.approx(0.25)
    assert assignment.crop_focus_y == pytest.approx(0.8)


def test_description_route_updates_page_and_revision(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_via_client(tmp_path, photo_count=1, slots=1)
    before = _stored_revision(page_id)

    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/description",
        data={"description": "First week of spring."},
    )

    assert response.status_code == 200
    assert "Description saved." in response.text
    assert _stored_revision(page_id) == before + 1

    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
    finally:
        database.close()
    assert page is not None
    assert page.description == "First week of spring."


def test_page_preview_route_returns_cached_jpeg(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_via_client(tmp_path, photo_count=1, slots=1)

    first = editor_client.get(
        f"/projects/{project_id}/pages/{page_id}/preview",
        params={"max_width": 320},
    )
    second = editor_client.get(
        f"/projects/{project_id}/pages/{page_id}/preview",
        params={"max_width": 320},
    )

    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    assert first.headers["cache-control"] == "no-cache"
    assert first.content
    assert second.content == first.content


def test_project_page_renders_sidebar_preview_thumbnails(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_via_client(tmp_path, photo_count=1, slots=1)

    response = editor_client.get(f"/projects/{project_id}?page={page_id}")

    assert response.status_code == 200
    assert f"/projects/{project_id}/pages/{page_id}/preview?max_width=320" in response.text
    assert "page-thumb-preview" in response.text
    assert 'hx-swap-oob="outerHTML"' not in response.text


def _seed_via_client(
    tmp_path: Path,
    *,
    photo_count: int = 4,
    slots: int | None = None,
) -> tuple[int, int, list[int], list[int]]:
    """Seed the client workspace and optionally assign photos to the first slots."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        project = ProjectService(database).create_project(
            name="Routes",
            page_count=1,
            start_date=datetime(2027, 1, 4),
        )

        source = tmp_path / "route-source"
        for index in range(photo_count):
            _write_photo(source / f"photo_{index:02d}.jpg", (index * 50, 0, 0))
        inventory = InventoryService(database)
        root = inventory.add_source_root(project.id, source)
        inventory.scan(project.id, source_root_id=root.id)

        with database.connect() as connection:
            page = PageRepository(connection).list(project.id)[0]

        editing = PageEditingService(database)
        layout_key = "four_quadrants" if (slots is None or slots > 2) else "two_columns"
        editing.change_layout(project.id, page.id, layout_key)

        with database.connect() as connection:
            page = PageRepository(connection).get(page.id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None
            photo_ids = [
                row["id"]
                for row in connection.execute("SELECT id FROM photos ORDER BY id").fetchall()
            ]
            slot_ids = [slot.id for slot in layout.slots]

        limit = slots if slots is not None else len(photo_ids)
        for photo_id, slot_id in zip(photo_ids[:limit], slot_ids[:limit], strict=True):
            editing.assign_to_empty_slot(project.id, page.id, slot_id, photo_id)

        return project.id, page.id, photo_ids, slot_ids
    finally:
        database.close()


def test_local_overrides_persist_and_invalidates_preview(tmp_path):
    database, editing, project_id, page_id, *_ = _seed(tmp_path)
    try:
        editing.set_local_overrides(
            project_id,
            page_id,
            hide_local_map=False,
            hide_calendar_strip=False,
            hide_description=False,
        )
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            assert page.hide_local_map is False
            revision = page.render_revision

        editing.set_local_overrides(
            project_id,
            page_id,
            hide_local_map=True,
            hide_calendar_strip=True,
            hide_description=True,
        )

        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
        assert page is not None
        assert page.hide_local_map is True
        assert page.hide_calendar_strip is True
        assert page.hide_description is True
        assert page.render_revision == revision + 1
    finally:
        database.close()


def test_populate_assigns_unused_photos_and_increments_revision(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        before = _page_revision(database, page_id)

        assigned = editing.populate(project_id, page_id)

        assert assigned == 4
        assert _page_revision(database, page_id) == before + 1
        with database.connect() as connection:
            assignments = AssignmentRepository(connection).list_by_page(page_id)
        assert {a.photo_id for a in assignments} == set(photo_ids)
        assert {a.slot_id for a in assignments} == set(slot_ids)

        # A second call is a no-op and does not bump the revision again.
        assert editing.populate(project_id, page_id) == 0
        assert _page_revision(database, page_id) == before + 1
    finally:
        database.close()


def test_populate_fills_only_empty_slots_in_order(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        editing.assign_to_empty_slot(project_id, page_id, slot_ids[0], photo_ids[0])

        assigned = editing.populate(project_id, page_id)

        assert assigned == 3
        with database.connect() as connection:
            by_slot = {
                assignment.slot_id: assignment.photo_id
                for assignment in AssignmentRepository(connection).list_by_page(page_id)
            }
        assert by_slot[slot_ids[0]] == photo_ids[0]
        assert [by_slot[slot] for slot in slot_ids[1:]] == photo_ids[1:]
    finally:
        database.close()


def test_populate_skips_unavailable_photos(tmp_path):
    database, editing, project_id, page_id, photo_ids, _ = _seed(tmp_path)
    try:
        with database.connect() as connection:
            PhotoRepository(connection).set_availability(photo_ids[0], False)

        assigned = editing.populate(project_id, page_id)

        assert assigned == 3
        with database.connect() as connection:
            assignments = AssignmentRepository(connection).list_by_page(page_id)
        assert photo_ids[0] not in {assignment.photo_id for assignment in assignments}
    finally:
        database.close()


def test_populate_skips_photos_used_on_other_pages(tmp_path):
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    try:
        project = ProjectService(database).create_project(
            name="Multi", page_count=2, start_date=datetime(2027, 1, 4)
        )
        source = tmp_path / "source"
        for index in range(4):
            _write_photo(source / f"photo_{index:02d}.jpg", (index * 50, 0, 0))
        inventory = InventoryService(database)
        root = inventory.add_source_root(project.id, source)
        inventory.scan(project.id, source_root_id=root.id)

        editing = PageEditingService(database)
        with database.connect() as connection:
            page_one, page_two = PageRepository(connection).list(project.id)[:2]
            photo_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM photos ORDER BY relative_path"
                ).fetchall()
            ]
        editing.change_layout(project.id, page_one.id, "four_quadrants")
        editing.change_layout(project.id, page_two.id, "four_quadrants")

        with database.connect() as connection:
            page_two = PageRepository(connection).get(page_two.id)
            assert page_two is not None and page_two.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page_two.layout_id)
            assert layout is not None
            other_slot = layout.slots[0]
        editing.assign_to_empty_slot(project.id, page_two.id, other_slot.id, photo_ids[0])

        assigned = editing.populate(project_id=project.id, page_id=page_one.id)

        # photo_ids[0] is already used on page two and must be skipped, so only
        # three of the four slots on page one can be filled.
        assert assigned == 3
        with database.connect() as connection:
            page_one_assignments = AssignmentRepository(connection).list_by_page(page_one.id)
        assigned_ids = {assignment.photo_id for assignment in page_one_assignments}
        assert photo_ids[0] not in assigned_ids
        assert assigned_ids == set(photo_ids[1:])
    finally:
        database.close()


def test_assign_selected_fills_empty_slots_in_order(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        before = _page_revision(database, page_id)

        assigned = editing.assign_selected(project_id, page_id, [photo_ids[2], photo_ids[0]])

        assert assigned == 2
        assert _page_revision(database, page_id) == before + 1
        with database.connect() as connection:
            by_slot = {
                assignment.slot_id: assignment.photo_id
                for assignment in AssignmentRepository(connection).list_by_page(page_id)
            }
        # First requested photo takes the first slot, second takes the next.
        assert by_slot[slot_ids[0]] == photo_ids[2]
        assert by_slot[slot_ids[1]] == photo_ids[0]
    finally:
        database.close()


def test_assign_selected_leaves_occupied_slots_untouched(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        editing.assign_to_empty_slot(project_id, page_id, slot_ids[0], photo_ids[0])

        assigned = editing.assign_selected(project_id, page_id, [photo_ids[2], photo_ids[3]])

        assert assigned == 2
        with database.connect() as connection:
            by_slot = {
                assignment.slot_id: assignment.photo_id
                for assignment in AssignmentRepository(connection).list_by_page(page_id)
            }
        assert by_slot[slot_ids[0]] == photo_ids[0]
        assert by_slot[slot_ids[1]] == photo_ids[2]
        assert by_slot[slot_ids[2]] == photo_ids[3]
    finally:
        database.close()


def test_assign_selected_skips_unavailable_and_used_photos(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        with database.connect() as connection:
            PhotoRepository(connection).set_availability(photo_ids[0], False)

        assigned = editing.assign_selected(
            project_id, page_id, [photo_ids[0], photo_ids[1], photo_ids[2]]
        )

        # photo_ids[0] is unavailable and skipped; the remaining two fill slots.
        assert assigned == 2
        with database.connect() as connection:
            assigned_ids = {
                assignment.photo_id
                for assignment in AssignmentRepository(connection).list_by_page(page_id)
            }
        assert photo_ids[0] not in assigned_ids
        assert assigned_ids == {photo_ids[1], photo_ids[2]}
    finally:
        database.close()


def test_assign_selected_skips_photos_used_on_other_pages(tmp_path):
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    try:
        project = ProjectService(database).create_project(
            name="Multi", page_count=2, start_date=datetime(2027, 1, 4)
        )
        source = tmp_path / "source"
        for index in range(4):
            _write_photo(source / f"photo_{index:02d}.jpg", (index * 50, 0, 0))
        inventory = InventoryService(database)
        root = inventory.add_source_root(project.id, source)
        inventory.scan(project.id, source_root_id=root.id)

        editing = PageEditingService(database)
        with database.connect() as connection:
            page_one, page_two = PageRepository(connection).list(project.id)[:2]
            photo_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM photos ORDER BY relative_path"
                ).fetchall()
            ]
        editing.change_layout(project.id, page_one.id, "four_quadrants")
        editing.change_layout(project.id, page_two.id, "four_quadrants")

        with database.connect() as connection:
            page_two = PageRepository(connection).get(page_two.id)
            assert page_two is not None and page_two.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page_two.layout_id)
            assert layout is not None
            other_slot = layout.slots[0]
        editing.assign_to_empty_slot(project.id, page_two.id, other_slot.id, photo_ids[0])

        assigned = editing.assign_selected(project.id, page_one.id, [photo_ids[0], photo_ids[1]])

        assert assigned == 1
        with database.connect() as connection:
            page_one_assignments = AssignmentRepository(connection).list_by_page(page_one.id)
        assigned_ids = {assignment.photo_id for assignment in page_one_assignments}
        assert photo_ids[0] not in assigned_ids
        assert assigned_ids == {photo_ids[1]}
    finally:
        database.close()


def test_assign_selected_noop_without_empty_slots(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        _assign_all(editing, project_id, page_id, photo_ids, slot_ids)
        before = _page_revision(database, page_id)

        assigned = editing.assign_selected(project_id, page_id, [photo_ids[0]])

        assert assigned == 0
        assert _page_revision(database, page_id) == before
    finally:
        database.close()


def test_assign_selected_empty_input_is_noop(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path)
    try:
        before = _page_revision(database, page_id)

        assert editing.assign_selected(project_id, page_id, []) == 0
        assert _page_revision(database, page_id) == before
    finally:
        database.close()


def test_populate_route_reports_assigned_and_refreshes_strip(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_via_client(tmp_path, photo_count=4, slots=3)
    before = _stored_revision(page_id)

    response = editor_client.post(f"/projects/{project_id}/pages/{page_id}/populate")

    assert response.status_code == 200
    assert "Populated 1 slot(s)." in response.text
    assert response.headers["HX-Trigger"] == "pcd:refresh-unused"
    assert _stored_revision(page_id) == before + 1

    # Filling again has nothing left to do.
    second = editor_client.post(f"/projects/{project_id}/pages/{page_id}/populate")
    assert second.status_code == 200
    assert "No empty slots or no unused photos to fill." in second.text


def test_assign_selected_route_assigns_and_refreshes_strip(editor_client, tmp_path):
    project_id, page_id, photo_ids, _ = _seed_via_client(tmp_path, photo_count=4, slots=0)
    before = _stored_revision(page_id)

    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign-selected",
        data={"photo_id": [str(photo_ids[2]), str(photo_ids[0])]},
    )

    assert response.status_code == 200
    assert "Assigned 2 photo(s)." in response.text
    assert response.headers["HX-Trigger"] == "pcd:refresh-unused"
    assert _stored_revision(page_id) == before + 1


def test_assign_selected_route_reports_noop(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_via_client(tmp_path, photo_count=4, slots=4)
    before = _stored_revision(page_id)

    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign-selected",
        data={"photo_id": [str(photo_ids[0])]},
    )

    assert response.status_code == 200
    assert "No empty slots or no selected photos to assign." in response.text
    assert response.headers["HX-Trigger"] == "pcd:refresh-unused"
    assert _stored_revision(page_id) == before


def test_editor_canvas_renders_slot_dropzones_with_geometry(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_via_client(tmp_path, photo_count=4, slots=3)

    response = editor_client.get(f"/projects/{project_id}/pages/{page_id}")

    assert response.status_code == 200
    text = response.text
    assert "page-preview-frame" in text
    # Four dropzones for the four_quadrants layout (one still empty).
    assert text.count("slot-dropzone") >= 4
    assert 'data-slot-id="' in text
    assert "slot-dropzone empty" in text
    # Inline percentage geometry is present.
    assert "left:" in text and "top:" in text and "width:" in text and "height:" in text


def test_editor_canvas_dropzones_mark_occupied_slots(editor_client, tmp_path):
    project_id, page_id, photo_ids, _ = _seed_via_client(tmp_path, photo_count=4, slots=1)

    response = editor_client.get(f"/projects/{project_id}/pages/{page_id}")

    assert response.status_code == 200
    # One occupied dropzone carries the assigned photo id.
    assert "slot-dropzone occupied" in response.text
    assert f'data-photo-id="{photo_ids[0]}"' in response.text
