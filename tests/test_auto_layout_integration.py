"""Integration tests for automatic layouts in the editing service and GUI."""

from __future__ import annotations

import re
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
from photo_composition_designer.layouts.loader import AUTO_LAYOUT_KEY, layout_choices
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.rendering import (
    collage_box_for_page,
    profile_from_project,
)
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    ProjectRepository,
)
from photo_composition_designer.project.services import ProjectService

# A catalogue layout with enough slots for the largest fixture used here.
_SEED_LAYOUT = "tiles_4_rows_5col"


@pytest.fixture()
def auto_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    return TestClient(create_app(GuiSettings(), sync_preview_worker=True))


def _write_photo(path: Path, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (10, 20, 30)).save(path)


def _seed(
    tmp_path: Path,
    *,
    photo_count: int,
    layout_key: str = _SEED_LAYOUT,
) -> tuple[WorkspaceDatabase, PageEditingService, int, int, list[int], list[int]]:
    """Create a one-page project with imported photos and a static layout."""
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    project = ProjectService(database).create_project(
        name="Auto",
        page_count=1,
        start_date=datetime(2027, 1, 4),
    )
    source = tmp_path / "source"
    for index in range(photo_count):
        _write_photo(source / f"photo_{index:02d}.jpg", 40, 30)
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    editing = PageEditingService(database)
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
        photo_ids = [row["id"] for row in connection.execute("SELECT id FROM photos ORDER BY id")]
    editing.change_layout(project.id, page.id, layout_key)

    with database.connect() as connection:
        page = PageRepository(connection).get(page.id)
        assert page is not None and page.layout_id is not None
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        assert layout is not None
        slot_ids = [slot.id for slot in layout.slots]
    return database, editing, project.id, page.id, photo_ids, slot_ids


def _assign(
    editing: PageEditingService,
    project_id: int,
    page_id: int,
    photo_ids: list[int],
    slot_ids: list[int],
) -> None:
    for photo_id, slot_id in zip(photo_ids, slot_ids, strict=False):
        editing.assign_to_empty_slot(project_id, page_id, slot_id, photo_id)


def _layout_for_page(database: WorkspaceDatabase, page_id: int):
    with database.connect() as connection:
        page = PageRepository(connection).get(page_id)
        assert page is not None and page.layout_id is not None
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        assert layout is not None
        assignments = AssignmentRepository(connection).list_by_page(page_id)
        return layout, assignments


@pytest.mark.parametrize("count", [0, 3, 7])
def test_change_to_auto_creates_one_slot_per_photo(tmp_path, count):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(
        tmp_path, photo_count=max(count, 1)
    )
    try:
        _assign(editing, project_id, page_id, photo_ids[:count], slot_ids)

        result = editing.change_layout(project_id, page_id, AUTO_LAYOUT_KEY)

        assert result.layout_key == AUTO_LAYOUT_KEY
        assert result.slot_count == count
        assert len(result.preserved) == count
        assert not result.has_displaced

        layout, assignments = _layout_for_page(database, page_id)
        assert layout.key == AUTO_LAYOUT_KEY
        assert [slot.slot_key for slot in layout.slots] == [
            f"auto_{index}" for index in range(count)
        ]
        assert {assignment.slot_id for assignment in assignments} == {
            slot.id for slot in layout.slots
        }
        assert {assignment.photo_id for assignment in assignments} == set(photo_ids[:count])
    finally:
        database.close()


def test_change_to_auto_preserves_crop_overrides(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path, photo_count=3)
    try:
        _assign(editing, project_id, page_id, photo_ids, slot_ids)
        editing.set_crop(
            project_id,
            page_id,
            slot_ids[0],
            crop_zoom=1.7,
            crop_focus_x=0.2,
            crop_focus_y=0.8,
        )

        editing.change_layout(project_id, page_id, AUTO_LAYOUT_KEY)

        layout, assignments = _layout_for_page(database, page_id)
        by_photo = {assignment.photo_id: assignment for assignment in assignments}
        preserved = by_photo[photo_ids[0]]
        assert preserved.crop_zoom == pytest.approx(1.7)
        assert preserved.crop_focus_x == pytest.approx(0.2)
        assert preserved.crop_focus_y == pytest.approx(0.8)
    finally:
        database.close()


def test_auto_snapshot_gets_fresh_version_and_invalidates_preview(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path, photo_count=2)
    try:
        _assign(editing, project_id, page_id, photo_ids[:2], slot_ids)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            before_revision = page.render_revision

        editing.change_layout(project_id, page_id, AUTO_LAYOUT_KEY)
        first_layout, _ = _layout_for_page(database, page_id)

        editing.change_layout(project_id, page_id, AUTO_LAYOUT_KEY)
        second_layout, _ = _layout_for_page(database, page_id)

        assert first_layout.version == 1
        assert second_layout.version == 2
        assert first_layout.id != second_layout.id
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            assert page.render_revision > before_revision
    finally:
        database.close()


def test_layout_choices_places_auto_first():
    choices = layout_choices()
    assert next(iter(choices)) == AUTO_LAYOUT_KEY
    assert choices[AUTO_LAYOUT_KEY].name == "Automatic"
    assert choices[AUTO_LAYOUT_KEY].slots == ()


def test_new_project_form_lists_auto_first(auto_client):
    response = auto_client.get("/projects/new")
    assert response.status_code == 200
    auto_index = response.text.find('value="auto"')
    other_index = response.text.find('value="single_full"')
    assert auto_index != -1
    assert other_index == -1 or auto_index < other_index
    assert "Automatic (from photos)" in response.text


def _seed_client(tmp_path: Path, *, photo_count: int = 4) -> tuple[int, int, list[int]]:
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        project = ProjectService(database).create_project(
            name="Routes",
            page_count=1,
            start_date=datetime(2027, 1, 4),
        )
        source = tmp_path / "route-source"
        for index in range(photo_count):
            _write_photo(source / f"photo_{index:02d}.jpg", 1600, 1200)
        inventory = InventoryService(database)
        root = inventory.add_source_root(project.id, source)
        inventory.scan(project.id, source_root_id=root.id)

        editing = PageEditingService(database)
        with database.connect() as connection:
            page = PageRepository(connection).list(project.id)[0]
            photo_ids = [
                row["id"] for row in connection.execute("SELECT id FROM photos ORDER BY id")
            ]
        editing.change_layout(project.id, page.id, _SEED_LAYOUT)
        with database.connect() as connection:
            page = PageRepository(connection).get(page.id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None
            slot_ids = [slot.id for slot in layout.slots]
        for photo_id, slot_id in zip(photo_ids, slot_ids, strict=False):
            editing.assign_to_empty_slot(project.id, page.id, slot_id, photo_id)
        return project.id, page.id, photo_ids
    finally:
        database.close()


def test_layout_preview_route_supports_auto(auto_client, tmp_path):
    project_id, page_id, _ = _seed_client(tmp_path, photo_count=3)

    response = auto_client.get(
        f"/projects/{project_id}/pages/{page_id}/layout/preview",
        params={"layout_key": "auto"},
    )

    assert response.status_code == 200
    assert "Switching to" in response.text
    assert "Automatic" in response.text
    assert "3 slots" in response.text
    assert "No photos will be displaced." in response.text


def test_layout_apply_route_supports_auto(auto_client, tmp_path):
    project_id, page_id, _ = _seed_client(tmp_path, photo_count=3)
    before = auto_client.get(f"/projects/{project_id}/pages/{page_id}").status_code

    response = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )

    assert response.status_code == 200
    assert "Layout changed." in response.text
    assert before == 200

    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None
            assert layout.key == "auto"
            assert len(layout.slots) == 3
    finally:
        database.close()


def test_editor_selector_lists_auto_first(auto_client, tmp_path):
    project_id, page_id, _ = _seed_client(tmp_path, photo_count=2)

    response = auto_client.get(f"/projects/{project_id}?page={page_id}")

    assert response.status_code == 200
    assert "Automatic (from photos)" in response.text
    assert response.text.find('value="auto"') < response.text.find('value="single_full"')


def _seed_auto_page(
    tmp_path: Path,
    *,
    photo_count: int,
    preassigned: int = 0,
) -> tuple[WorkspaceDatabase, PageEditingService, int, int, list[int], list[int]]:
    """Create a one-page project switched to the automatic layout.

    ``preassigned`` photos are placed on the static seed layout first so the
    automatic snapshot starts with that many slots. The returned slot ids are
    the slots of the resulting automatic snapshot, in reading order.
    """
    database, editing, project_id, page_id, photo_ids, seed_slots = _seed(
        tmp_path, photo_count=photo_count
    )
    _assign_photos(editing, project_id, page_id, photo_ids[:preassigned], seed_slots)
    editing.change_layout(project_id, page_id, AUTO_LAYOUT_KEY)
    return (
        database,
        editing,
        project_id,
        page_id,
        photo_ids,
        editing_layout_slot_ids(database, page_id),
    )


def editing_layout_slot_ids(database: WorkspaceDatabase, page_id: int) -> list[int]:
    """Return the current layout slot ids of a page in slot order."""
    layout, _ = _layout_for_page(database, page_id)
    return [slot.id for slot in layout.slots]


def _assign_photos(
    editing: PageEditingService,
    project_id: int,
    page_id: int,
    photo_ids: list[int],
    slot_ids: list[int],
) -> None:
    for photo_id, slot_id in zip(photo_ids, slot_ids, strict=False):
        editing.assign_to_empty_slot(project_id, page_id, slot_id, photo_id)


def test_auto_add_fills_existing_empty_slot(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed_auto_page(
        tmp_path, photo_count=5, preassigned=2
    )
    try:
        first_layout, assignments = _layout_for_page(database, page_id)
        empty_slot = first_layout.slots[-1].id
        editing.remove(project_id, page_id, empty_slot)

        regenerated = editing.auto_add(project_id, page_id, photo_ids[4])

        assert regenerated is False
        layout, assignments = _layout_for_page(database, page_id)
        assert layout.id == first_layout.id
        assert len(layout.slots) == 2
        by_slot = {assignment.slot_id: assignment.photo_id for assignment in assignments}
        assert by_slot[empty_slot] == photo_ids[4]
        assert len(by_slot) == 2
    finally:
        database.close()


def test_auto_add_without_empty_slot_regenerates_and_preserves_crop(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed_auto_page(
        tmp_path, photo_count=4, preassigned=2
    )
    try:
        editing.set_crop(
            project_id,
            page_id,
            slot_ids[0],
            crop_zoom=1.9,
            crop_focus_x=0.3,
            crop_focus_y=0.6,
        )
        first_layout, _ = _layout_for_page(database, page_id)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            revision_before = page.render_revision

        regenerated = editing.auto_add(project_id, page_id, photo_ids[2])

        assert regenerated is True
        layout, assignments = _layout_for_page(database, page_id)
        assert layout.id != first_layout.id
        assert len(layout.slots) == 3
        by_photo = {assignment.photo_id: assignment for assignment in assignments}
        assert set(by_photo) == set(photo_ids[:3])
        preserved = by_photo[photo_ids[0]]
        assert preserved.crop_zoom == pytest.approx(1.9)
        assert preserved.crop_focus_x == pytest.approx(0.3)
        assert preserved.crop_focus_y == pytest.approx(0.6)
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            assert page.render_revision > revision_before
    finally:
        database.close()


def test_auto_add_rejects_non_auto_page_and_unavailable_photo(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path, photo_count=4)
    try:
        with pytest.raises(ProjectError):
            editing.auto_add(project_id, page_id, photo_ids[0])

        editing.change_layout(project_id, page_id, AUTO_LAYOUT_KEY)
        with database.connect() as connection:
            connection.execute("UPDATE photos SET available = 0 WHERE id = ?", (photo_ids[0],))
        with pytest.raises(ProjectError):
            editing.auto_add(project_id, page_id, photo_ids[0])
    finally:
        database.close()


def test_remove_leaves_hole_and_reflow_restores_slots(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed_auto_page(
        tmp_path, photo_count=4, preassigned=3
    )
    try:
        first_layout, _ = _layout_for_page(database, page_id)
        removed_slot = first_layout.slots[1]

        assert editing.remove(project_id, page_id, removed_slot.id) is True

        layout, assignments = _layout_for_page(database, page_id)
        assert layout.id == first_layout.id
        assert len(layout.slots) == 3
        assert removed_slot.id not in {assignment.slot_id for assignment in assignments}
        assert len(assignments) == 2

        assert editing.auto_reflow(project_id, page_id) is True

        layout, assignments = _layout_for_page(database, page_id)
        assert layout.id != first_layout.id
        assert len(layout.slots) == 2
        assert {assignment.slot_id for assignment in assignments} == {
            slot.id for slot in layout.slots
        }
        assert len(assignments) == 2
    finally:
        database.close()


def test_auto_remove_empty_drops_holes_and_is_noop_without_holes(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed_auto_page(
        tmp_path, photo_count=4, preassigned=3
    )
    try:
        first_layout, _ = _layout_for_page(database, page_id)

        assert editing.auto_remove_empty(project_id, page_id) is False

        removed_slot = first_layout.slots[0]
        editing.remove(project_id, page_id, removed_slot.id)
        assert editing.auto_remove_empty(project_id, page_id) is True

        layout, assignments = _layout_for_page(database, page_id)
        assert len(layout.slots) == 2
        assert len(assignments) == 2
        assert {assignment.slot_id for assignment in assignments} == {
            slot.id for slot in layout.slots
        }

        assert editing.auto_remove_empty(project_id, page_id) is False
    finally:
        database.close()


def test_auto_reflow_returns_false_for_static_layout(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed(tmp_path, photo_count=3)
    try:
        assert editing.auto_reflow(project_id, page_id) is False
        assert editing.auto_remove_empty(project_id, page_id) is False
    finally:
        database.close()


def test_auto_add_route_reports_reflow_and_lists_photo(auto_client, tmp_path):
    project_id, page_id, photo_ids = _seed_client(tmp_path, photo_count=3)
    auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )

    response = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/auto/add",
        data={"photo_id": photo_ids[0]},
    )

    assert response.status_code == 200
    assert "Photo added and layout reflowed." in response.text
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None
            assert len(layout.slots) == 4
            assignments = connection.execute(
                "SELECT photo_id FROM assignments WHERE page_id = ? ORDER BY slot_id",
                (page_id,),
            ).fetchall()
            assert photo_ids[0] in {row["photo_id"] for row in assignments}
    finally:
        database.close()


def test_auto_add_route_rejects_non_auto_page(auto_client, tmp_path):
    project_id, page_id, photo_ids = _seed_client(tmp_path, photo_count=2)

    response = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/auto/add",
        data={"photo_id": photo_ids[0]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "automatic" in response.headers["location"]


def test_auto_page_shows_reflow_and_add_controls(auto_client, tmp_path):
    project_id, page_id, photo_ids = _seed_client(tmp_path, photo_count=2)
    auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )

    response = auto_client.get(f"/projects/{project_id}?page={page_id}")

    assert response.status_code == 200
    assert "/auto/reflow" in response.text
    assert "/auto/remove-empty" in response.text
    assert "/auto/add" in response.text
    assert "Reflow" in response.text
    assert "Remove empty slots" in response.text


def _create_auto_project(tmp_path: Path, *, page_count: int = 1) -> int:
    """Create a project whose pages all use the empty automatic layout."""
    source = tmp_path / f"auto-source-{page_count}"
    source.mkdir(parents=True, exist_ok=True)
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    response = client.post(
        "/projects",
        data={
            "name": "Empty auto",
            "page_count": str(page_count),
            "start_date": "2027-01-04",
            "layout_key": "auto",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    return int(location.split("/projects/", 1)[1].split("?", 1)[0])


def test_auto_page_without_slots_uses_collage_area_dropzone(auto_client, tmp_path):
    # A project created with the auto default gets an empty auto snapshot on
    # every page, which is the canonical "empty auto page" state. The drop zone
    # must cover only the collage content box, not the entire page frame.
    empty_project_id = _create_auto_project(tmp_path, page_count=1)
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).list(empty_project_id)[0]
            project = ProjectRepository(connection).get(empty_project_id)
            assert project is not None
            box = collage_box_for_page(page, profile_from_project(project))
    finally:
        database.close()

    response = auto_client.get(f"/projects/{empty_project_id}?page={page.id}")

    assert response.status_code == 200
    assert "auto-canvas-dropzone" in response.text
    assert "Drop a photo to start the layout" in response.text
    match = re.search(r'class="auto-canvas-dropzone"[^>]*style="([^"]+)"', response.text)
    assert match is not None, "empty auto dropzone must carry inline collage geometry"
    style = match.group(1)
    expected = {
        "left": box.left / box.page_width * 100.0,
        "top": box.top / box.page_height * 100.0,
        "width": box.width / box.page_width * 100.0,
        "height": box.height / box.page_height * 100.0,
    }
    for name, value in expected.items():
        found = re.search(rf"{name}:\s*([\d.]+)%", style)
        assert found is not None, f"missing {name} in dropzone style"
        assert float(found.group(1)) == pytest.approx(value, abs=1e-3)
    # The collage box leaves room for margins/calendar, so it is not full-frame.
    assert expected["width"] < 100.0
    assert expected["height"] < 100.0


def test_static_page_has_no_auto_controls(auto_client, tmp_path):
    project_id, page_id, _ = _seed_client(tmp_path, photo_count=2)

    response = auto_client.get(f"/projects/{project_id}?page={page_id}")

    assert response.status_code == 200
    assert "/auto/reflow" not in response.text
    assert "auto-canvas-dropzone" not in response.text


def test_auto_add_route_reports_reflow_when_no_hole(auto_client, tmp_path):
    project_id, page_id, photo_ids = _seed_client(tmp_path, photo_count=3)
    auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )

    first = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/auto/add",
        data={"photo_id": photo_ids[0]},
    )
    second = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/auto/add",
        data={"photo_id": photo_ids[1]},
    )

    assert "Photo added and layout reflowed." in first.text
    assert "Photo added and layout reflowed." in second.text


def test_auto_reflow_and_remove_empty_routes(auto_client, tmp_path):
    project_id, page_id, photo_ids = _seed_client(tmp_path, photo_count=3)
    auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )
    first = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/auto/add",
        data={"photo_id": photo_ids[0]},
    )
    second = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/auto/add",
        data={"photo_id": photo_ids[1]},
    )
    assert "Photo added and layout reflowed." in first.text
    assert "Photo added and layout reflowed." in second.text

    removed = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/remove",
        data={"slot_id": _first_slot_id(tmp_path, page_id)},
    )
    assert removed.status_code == 200

    empty = auto_client.post(f"/projects/{project_id}/pages/{page_id}/auto/remove-empty")
    assert empty.status_code == 200
    assert "Empty slots removed." in empty.text

    reflow = auto_client.post(f"/projects/{project_id}/pages/{page_id}/auto/reflow")
    assert reflow.status_code == 200
    assert "Layout reflowed." in reflow.text

    empty = auto_client.post(f"/projects/{project_id}/pages/{page_id}/auto/remove-empty")
    assert empty.status_code == 200
    assert "No empty slots to remove." in empty.text


def test_auto_add_many_adds_all_selected_and_reflows(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed_auto_page(
        tmp_path, photo_count=5, preassigned=2
    )
    try:
        added, regenerated = editing.auto_add_many(project_id, page_id, photo_ids[2:5])

        assert added == 3
        assert regenerated is True
        layout, assignments = _layout_for_page(database, page_id)
        assert len(layout.slots) == 5
        assert {assignment.photo_id for assignment in assignments} == set(photo_ids[:5])
    finally:
        database.close()


def test_auto_add_many_fills_empty_slot_before_reflowing(tmp_path):
    database, editing, project_id, page_id, photo_ids, slot_ids = _seed_auto_page(
        tmp_path, photo_count=5, preassigned=2
    )
    try:
        first_layout, _ = _layout_for_page(database, page_id)
        editing.remove(project_id, page_id, first_layout.slots[1].id)

        added, regenerated = editing.auto_add_many(project_id, page_id, photo_ids[2:4])

        assert added == 2
        assert regenerated is True
        layout, assignments = _layout_for_page(database, page_id)
        assert len(layout.slots) == 3
        assert {assignment.photo_id for assignment in assignments} == {
            photo_ids[0],
            photo_ids[2],
            photo_ids[3],
        }
    finally:
        database.close()


def test_auto_fill_unused_fills_empty_slot_without_reflow(tmp_path):
    database, editing, project_id, page_id, photo_ids, _slot_ids = _seed_auto_page(
        tmp_path, photo_count=5, preassigned=2
    )
    try:
        first_layout, _ = _layout_for_page(database, page_id)
        editing.remove(project_id, page_id, first_layout.slots[0].id)

        added, regenerated = editing.auto_fill_unused(project_id, page_id, 1)

        assert added == 1
        assert regenerated is False
        layout, assignments = _layout_for_page(database, page_id)
        assert len(layout.slots) == 2
        assert len(assignments) == 2
        assert {assignment.photo_id for assignment in assignments} == set(photo_ids[:2])
    finally:
        database.close()


def test_auto_fill_unused_reflows_when_more_photos_than_holes(tmp_path):
    database, editing, project_id, page_id, photo_ids, _slot_ids = _seed_auto_page(
        tmp_path, photo_count=5, preassigned=2
    )
    try:
        first_layout, _ = _layout_for_page(database, page_id)
        editing.remove(project_id, page_id, first_layout.slots[0].id)

        added, regenerated = editing.auto_fill_unused(project_id, page_id, 3)

        assert added == 3
        assert regenerated is True
        layout, assignments = _layout_for_page(database, page_id)
        assert len(layout.slots) == 4
        assert {assignment.photo_id for assignment in assignments} == set(photo_ids[:4])
    finally:
        database.close()


def test_auto_fill_unused_without_unused_photos_is_noop(tmp_path):
    database, editing, project_id, page_id, _photo_ids, _slot_ids = _seed_auto_page(
        tmp_path, photo_count=2, preassigned=2
    )
    try:
        added, regenerated = editing.auto_fill_unused(project_id, page_id, 5)

        assert added == 0
        assert regenerated is False
        layout, assignments = _layout_for_page(database, page_id)
        assert len(assignments) == 2
        assert len(layout.slots) == 2
    finally:
        database.close()


@pytest.mark.parametrize("limit", [0, -1, 100])
def test_auto_fill_unused_rejects_out_of_range_limit(tmp_path, limit):
    database, editing, project_id, page_id, _photo_ids, _slot_ids = _seed_auto_page(
        tmp_path, photo_count=3, preassigned=1
    )
    try:
        with pytest.raises(ProjectError):
            editing.auto_fill_unused(project_id, page_id, limit)
    finally:
        database.close()


def test_auto_fill_unused_rejects_non_auto_page(tmp_path):
    database, editing, project_id, page_id, _photo_ids, _slot_ids = _seed(
        tmp_path, photo_count=3
    )
    try:
        with pytest.raises(ProjectError):
            editing.auto_fill_unused(project_id, page_id, 2)
    finally:
        database.close()


def test_auto_fill_route_adds_unused_photos(auto_client, tmp_path):
    project_id, page_id, photo_ids = _seed_client(tmp_path, photo_count=4)
    auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )
    auto_client.post(f"/projects/{project_id}/pages/{page_id}/assignments/clear")
    auto_client.post(f"/projects/{project_id}/pages/{page_id}/auto/reflow")

    response = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/auto/fill",
        data={"limit": 2},
    )

    assert response.status_code == 200
    assert "Added 2 photo(s) and layout reflowed." in response.text
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None
            assert len(layout.slots) == 2
            assignments = connection.execute(
                "SELECT photo_id FROM assignments WHERE page_id = ?", (page_id,)
            ).fetchall()
            assert {row["photo_id"] for row in assignments} == set(photo_ids[:2])
    finally:
        database.close()


def test_auto_fill_control_rendered_only_with_unused_photos(auto_client, tmp_path):
    project_id, page_id, _photo_ids = _seed_client(tmp_path, photo_count=4)
    auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )

    # All photos assigned to the auto layout: no unused photos, no control.
    assigned_view = auto_client.get(f"/projects/{project_id}?page={page_id}")
    assert "Fill slots with unused photos" not in assigned_view.text

    # Clearing assignments frees every photo, so the control appears.
    auto_client.post(f"/projects/{project_id}/pages/{page_id}/assignments/clear")
    unused_view = auto_client.get(f"/projects/{project_id}?page={page_id}")
    assert "Fill slots with unused photos" in unused_view.text
    assert "/auto/fill" in unused_view.text
    assert 'value="5"' in unused_view.text
    assert 'max="99"' in unused_view.text


def test_auto_add_route_adds_multiple_photos(auto_client, tmp_path):
    project_id, page_id, photo_ids = _seed_client(tmp_path, photo_count=4)
    auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )
    auto_client.post(f"/projects/{project_id}/pages/{page_id}/assignments/clear")
    auto_client.post(f"/projects/{project_id}/pages/{page_id}/auto/reflow")

    response = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/auto/add",
        data={"photo_id": [str(photo_ids[0]), str(photo_ids[1])]},
    )

    assert response.status_code == 200
    assert "2 photos added and layout reflowed." in response.text
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None
            assert len(layout.slots) == 2
    finally:
        database.close()


def test_assign_selected_route_adds_all_photos_on_auto_page(auto_client, tmp_path):
    project_id, page_id, photo_ids = _seed_client(tmp_path, photo_count=4)
    auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/layout",
        data={"layout_key": "auto", "confirm": "1"},
    )
    auto_client.post(f"/projects/{project_id}/pages/{page_id}/assignments/clear")
    auto_client.post(f"/projects/{project_id}/pages/{page_id}/auto/reflow")

    response = auto_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign-selected",
        data={"photo_id": [str(photo_ids[0]), str(photo_ids[1])]},
    )

    assert response.status_code == 200
    assert "Added 2 photos and layout reflowed." in response.text
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None
            assert len(layout.slots) == 2
            assignments = connection.execute(
                "SELECT photo_id FROM assignments WHERE page_id = ?", (page_id,)
            ).fetchall()
            assert {row["photo_id"] for row in assignments} == {
                photo_ids[0],
                photo_ids[1],
            }
    finally:
        database.close()


def _first_slot_id(tmp_path: Path, page_id: int) -> int:
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None and layout.slots
            return layout.slots[0].id
    finally:
        database.close()
