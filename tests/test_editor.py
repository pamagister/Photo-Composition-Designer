"""Browser-level tests for the three-panel editor interaction model."""

from __future__ import annotations

import re
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
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
)
from photo_composition_designer.project.services import ProjectService


@pytest.fixture()
def editor_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    app = create_app(GuiSettings(), sync_preview_worker=True)
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


def _assignment_count(project_id: int) -> int:
    """Return the number of assignments stored for a project."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            return len(AssignmentRepository(connection).list_by_project(project_id))
    finally:
        database.close()


def _page_revision(page_id: int) -> int:
    """Return the stored render revision for one page."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            assert page is not None
            return page.render_revision
    finally:
        database.close()


def test_editor_shell_renders_compact_editor_and_photo_filter(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    response = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert response.status_code == 200
    assert "editor-shell" in response.text
    assert "editor-sidebar" in response.text
    assert "editor-bottom" in response.text
    assert "Photos" in response.text
    assert 'id="photo-filter"' in response.text
    assert "All photos" in response.text
    assert "editor-layout-panel" in response.text


def test_preview_action_keeps_selected_page_and_refreshes_large_preview(editor_client, tmp_path):
    project_id, first_page_id, _, _ = _seed_project(tmp_path, page_count=2)
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            second_page_id = PageRepository(connection).list(project_id)[1].id
    finally:
        database.close()

    assert second_page_id != first_page_id
    response = editor_client.get(
        f"/projects/{project_id}/preview?page={second_page_id}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert f"page={second_page_id}" in response.headers["location"]
    assert "previewed=1" in response.headers["location"]

    preview = editor_client.get(f"/projects/{project_id}/pages/{second_page_id}/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"

    page = editor_client.get(f"/projects/{project_id}?page={second_page_id}")
    assert f'href="/projects/{project_id}/preview?page={second_page_id}"' in page.text


def test_assign_photo_via_route(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    assert response.status_code == 200
    assert "Photo assigned" in response.text
    assert f"/pages/{page_id}/preview?v=2" in response.text

    preview = editor_client.get(f"/projects/{project_id}/pages/{page_id}/preview?max_width=200")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"


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


def test_clear_page_assignments_via_route(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path, slots_per_page=2)
    for slot_id, photo_id in zip(slot_ids, photo_ids, strict=False):
        editor_client.post(
            f"/projects/{project_id}/pages/{page_id}/assign",
            data={"slot_id": slot_id, "photo_id": photo_id},
        )
    assert _assignment_count(project_id) == 2
    revision = _page_revision(page_id)

    response = editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assignments/clear",
    )

    assert response.status_code == 200
    assert "Removed 2 assignment(s)." in response.text
    assert _assignment_count(project_id) == 0
    assert _page_revision(page_id) == revision + 1
    # The layout itself is preserved.
    assert 'class="layout-change"' in response.text


def test_clear_project_assignments_via_route(editor_client, tmp_path):
    project_id, first_page_id, photo_ids, slot_ids = _seed_project(
        tmp_path, page_count=2, slots_per_page=2
    )
    second_page_id = _list_page_ids(project_id)[1]
    second_slot_ids = _page_slot_ids(project_id, second_page_id)
    editor_client.post(
        f"/projects/{project_id}/pages/{first_page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    editor_client.post(
        f"/projects/{project_id}/pages/{second_page_id}/assign",
        data={"slot_id": second_slot_ids[0], "photo_id": photo_ids[1]},
    )
    assert _assignment_count(project_id) == 2

    response = editor_client.post(
        f"/projects/{project_id}/assignments/clear",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/projects/{project_id}?assignments=1"
    assert _assignment_count(project_id) == 0
    project_page = editor_client.get(f"/projects/{project_id}?assignments=1&page={first_page_id}")
    assert "Project assignments cleared." in project_page.text


def test_page_layout_actions_include_confirming_clear_button(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_project(tmp_path)
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")

    assert page.status_code == 200
    assert 'class="danger icon-button layout-clear-button"' in page.text
    assert f'hx-post="/projects/{project_id}/pages/{page_id}/assignments/clear"' in page.text
    assert "Remove all photo assignments from this page?" in page.text


def test_extras_menu_offers_clear_all_assignments(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_project(tmp_path)
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")

    assert page.status_code == 200
    assert 'class="nav-dropdown-danger"' in page.text
    assert f'action="/projects/{project_id}/assignments/clear"' in page.text
    assert "Clear assignments" in page.text
    assert "Remove all photo assignments for this project?" in page.text


def test_top_menus_load_auto_close_script(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_project(tmp_path)
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")

    assert page.status_code == 200
    assert "/static/nav.js" in page.text
    # At least the Settings and Extras menus exist for the script to coordinate.
    assert page.text.count('class="nav-dropdown"') >= 2


def test_projects_navigation_is_a_prominent_button(editor_client, tmp_path):
    project_id, page_id, _, _ = _seed_project(tmp_path)
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")

    assert page.status_code == 200
    assert '<a class="button nav-projects" href="/projects">Projects</a>' in page.text


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


def test_assign_allows_reusing_photo(editor_client, tmp_path):
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
    assert response.status_code == 200
    assert "Photo assigned" in response.text


def test_all_photos_filter_marks_repeated_assignments(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path)
    for slot_id in slot_ids:
        response = editor_client.post(
            f"/projects/{project_id}/pages/{page_id}/assign",
            data={"slot_id": slot_id, "photo_id": photo_ids[0]},
        )
        assert response.status_code == 200

    unused = editor_client.get(f"/projects/{project_id}/pages/{page_id}/unused")
    assert f'data-photo-id="{photo_ids[0]}"' not in unused.text
    assert f'data-photo-id="{photo_ids[1]}"' in unused.text

    all_photos = editor_client.get(f"/projects/{project_id}/pages/{page_id}/unused?filter=all")
    assert all_photos.status_code == 200
    assert 'data-use-count="2"' in all_photos.text
    assert 'title="This photo is used 2 times"' in all_photos.text
    assert 'id="photo-filter"' in all_photos.text


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


def test_empty_slot_can_reuse_a_photo_when_none_are_unused(editor_client, tmp_path):
    project_id, page_id, photo_ids, slot_ids = _seed_project(tmp_path, photo_count=1)
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/assign",
        data={"slot_id": slot_ids[0], "photo_id": photo_ids[0]},
    )
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert page.status_code == 200
    assert "No unused photos." in page.text
    assert f'id="assign-photo-{slot_ids[1]}"' in page.text
    assert f'<option value="{photo_ids[0]}">' in page.text


def _list_page_ids(project_id: int) -> list[int]:
    """Return the page ids for a project from the isolated workspace."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            return [page.id for page in PageRepository(connection).list(project_id)]
    finally:
        database.close()


def _page_slot_ids(project_id: int, page_id: int) -> list[int]:
    """Return the layout slot ids assigned to one page."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.layout_id is None:
                return []
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            return [slot.id for slot in layout.slots] if layout is not None else []
    finally:
        database.close()


def test_empty_description_shows_preview_overlay(editor_client, tmp_path):
    # Page index 1 is not a title page, so its description is rendered and empty.
    project_id, _, _, _ = _seed_project(tmp_path, page_count=2)
    page_id = _list_page_ids(project_id)[1]
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert page.status_code == 200
    assert 'class="preview-notice"' in page.text


def test_preview_overlay_hidden_when_description_present(editor_client, tmp_path):
    project_id, _, _, _ = _seed_project(tmp_path, page_count=2)
    page_id = _list_page_ids(project_id)[1]
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/description",
        data={"description": "A short note."},
    )
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert 'class="preview-notice"' not in page.text


def test_preview_overlay_hidden_by_local_override(editor_client, tmp_path):
    project_id, _, _, _ = _seed_project(tmp_path, page_count=2)
    page_id = _list_page_ids(project_id)[1]
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/overrides",
        data={"hide_description": "1"},
        headers={"HX-Request": "true"},
    )
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert 'class="preview-notice"' not in page.text


def test_description_overlay_is_a_jump_target_not_a_photo_dropzone(editor_client, tmp_path):
    project_id, _, _, _ = _seed_project(tmp_path, page_count=2)
    page_id = _list_page_ids(project_id)[1]
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert page.status_code == 200

    match = re.search(r'<button[^>]*class="description-overlay"[^>]*>', page.text)
    assert match is not None
    tag = match.group(0)
    assert 'data-description-overlay="1"' in tag
    # The description area must not behave like a slot dropzone.
    assert "data-slot-id" not in tag
    assert "dropzone-hint" not in tag
    assert "Drop photo" not in tag

    style = re.search(r'style="([^"]+)"', tag)
    assert style is not None
    assert "left: 0.0%" in style.group(1)
    for property_name in ("top", "width", "height"):
        assert f"{property_name}:" in style.group(1)


def test_description_overlay_hidden_by_local_override(editor_client, tmp_path):
    project_id, _, _, _ = _seed_project(tmp_path, page_count=2)
    page_id = _list_page_ids(project_id)[1]
    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/overrides",
        data={"hide_description": "1"},
        headers={"HX-Request": "true"},
    )
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert 'data-description-overlay="1"' not in page.text


def test_page_tile_shows_status_hints(editor_client, tmp_path):
    project_id, title_page_id, photo_ids, _ = _seed_project(
        tmp_path, page_count=2, slots_per_page=2
    )
    page_id = _list_page_ids(project_id)[1]  # non-title page
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert page.status_code == 200
    # Empty rendered description and empty slots both flag the non-title page only.
    assert page.text.count('aria-label="Page description is empty"') == 1
    assert 'aria-label="Not all slots are filled"' in page.text
    assert f'id="page-thumb-meta-{page_id}"' in page.text
    # The title page suppresses the description hint.
    title_slice = page.text[page.text.index(f'id="page-thumb-meta-{title_page_id}"') :]
    assert 'aria-label="Page description is empty"' not in title_slice[:400]


def test_page_tile_hints_clear_after_edits(editor_client, tmp_path):
    project_id, _, photo_ids, _ = _seed_project(tmp_path, page_count=2, slots_per_page=2)
    page_id = _list_page_ids(project_id)[1]
    response = None
    for slot_id in _page_slot_ids(project_id, page_id):
        response = editor_client.post(
            f"/projects/{project_id}/pages/{page_id}/assign",
            data={"slot_id": slot_id, "photo_id": photo_ids[0]},
        )
    # The out-of-band tile meta refresh drops the incomplete hint once full.
    assert 'id="page-thumb-meta-' in response.text
    assert 'aria-label="Not all slots are filled"' not in response.text

    editor_client.post(
        f"/projects/{project_id}/pages/{page_id}/description",
        data={"description": "A short note."},
    )
    page = editor_client.get(f"/projects/{project_id}?page={page_id}")
    assert 'aria-label="Page description is empty"' not in page.text
