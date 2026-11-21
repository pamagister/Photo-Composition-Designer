"""Integration tests for automatic layouts in the editing service and GUI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from starlette.testclient import TestClient

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.layouts.loader import AUTO_LAYOUT_KEY, layout_choices
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
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
