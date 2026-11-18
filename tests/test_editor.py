"""Browser-level tests for the three-panel editor interaction model."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from starlette.testclient import TestClient

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.repositories import (
    LayoutRepository,
    PageRepository,
)
from photo_composition_designer.project.services import ProjectService


@pytest.fixture()
def editor_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    app = create_app(GuiSettings())
    return TestClient(app)


def _write_photo(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _seed_project(
    tmp_path: Path,
    *,
    page_count: int = 1,
    photo_count: int = 2,
    slots_per_page: int = 2,
) -> tuple[int, int, list[int], list[int]]:
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    service = ProjectService(database)
    project = service.create_project(
        name="Editor",
        page_count=page_count,
        start_date=__import__("datetime").datetime(2027, 1, 4),
        settings={},
        output_profile={},
        import_metadata={"source": "test"},
    )

    source = tmp_path / "source"
    for index in range(photo_count):
        _write_photo(source / f"photo_{index:02d}.jpg", (index * 40, 0, 0))
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    with database.transaction() as connection:
        layout_repo = LayoutRepository(connection)
        page_repo = PageRepository(connection)
        pages = page_repo.list(project.id)
        for page in pages:
            slots = [
                LayoutSlot(
                    id=0,
                    layout_id=0,
                    slot_key=f"slot_{i}",
                    position=i,
                    x=i * (1.0 / slots_per_page),
                    y=0.0,
                    width=1.0 / slots_per_page,
                    height=1.0,
                    z_index=0,
                    crop_mode="cover",
                )
                for i in range(slots_per_page)
            ]
            layout = layout_repo.add(f"layout_{page.page_index}", 1, "Test", slots)
            page_repo.set_layout(page.id, layout.id, 1)

    with database.connect() as connection:
        photo_ids = [
            row["id"] for row in connection.execute("SELECT id FROM photos ORDER BY id").fetchall()
        ]
        slot_ids = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM layout_slots ORDER BY position LIMIT ?",
                (slots_per_page,),
            ).fetchall()
        ]

    return project.id, pages[0].id, photo_ids, slot_ids


def test_editor_shell_renders_three_panels(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    response = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert response.status_code == 200
    assert "editor-shell" in response.text
    assert "editor-sidebar" in response.text
    assert "editor-bottom" in response.text
    assert "Unused photos" in response.text


def test_assign_photo_via_route(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    assert response.status_code == 200
    assert "Photo assigned" in response.text


def test_remove_photo_via_route(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/remove",
        data={"slot_id": slot_ids[0]},
    )
    assert response.status_code == 200
    assert "Photo removed" in response.text


def test_swap_photos_via_route(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[1], "photo_id": photo_ids[1]},
    )
    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/swap",
        data={"slot_a": slot_ids[0], "slot_b": slot_ids[1]},
    )
    assert response.status_code == 200
    assert "Photos swapped" in response.text


def test_unused_pool_reflects_assignments(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    response = editor_client.get(f"/projects/{project_id}/pages/{page_id}/unused")
    assert response.status_code == 200
    assert "unused-item" in response.text

    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    response = editor_client.get(f"/projects/{project_id}/pages/{page_id}/unused")
    assert f'data-photo-id="{photo_ids[0]}"' not in response.text
    assert f'data-photo-id="{photo_ids[1]}"' in response.text


def test_assign_rejects_duplicate_photo(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[1], "photo_id": photo_ids[0]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "already" in response.headers.get("location", "")


def test_replace_photo_via_route(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/replace",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[1]},
    )
    assert response.status_code == 200
    assert "Photo replaced" in response.text


def test_occupied_slot_exposes_keyboard_replace_and_move(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert page.status_code == 200

    markup = page.text
    assert f'hx-post="/projects/{project_id}/pages/{page_id}/replace"' in markup
    assert f'hx-post="/projects/{project_id}/pages/{page_id}/swap"' in markup
    assert f'name="slot_a" value="{slot_ids[0]}"' in markup
    assert 'name="slot_b"' in markup
    assert f'<option value="{slot_ids[1]}">slot_1</option>' in markup


def test_slots_use_group_semantics_instead_of_button_role(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert page.status_code == 200

    markup = page.text
    assert 'role="button"' not in markup
    assert 'class="slot empty"' in markup
    assert 'aria-label="Slot slot_0: empty"' in markup
    assert f'id="assign-photo-{slot_ids[0]}"' in markup


def test_project_page_has_skip_link_and_live_notice(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_project(tmp_path)
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert page.status_code == 200
    assert 'class="skip-link" href="#main"' in page.text
    assert '<main id="main">' in page.text
    assert 'aria-live="polite"' in page.text


def test_empty_slot_without_unused_photos_has_no_assign_form(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path, photo_count=1)
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert page.status_code == 200
    assert "All photos are assigned." in page.text
    assert f'id="assign-photo-{slot_ids[1]}"' not in page.text
