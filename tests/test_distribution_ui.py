"""Tests for the distribution preview, confirmation and review flow."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from PIL import Image
from starlette.testclient import TestClient

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.layouts.loader import AUTO_LAYOUT_KEY
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    return TestClient(create_app(GuiSettings(), sync_preview_worker=True))


def _write_photo(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _database() -> WorkspaceDatabase:
    return WorkspaceDatabase(data_dir() / "workspace.sqlite3")


def _assignment_count(project_id: int) -> int:
    with _database().connect() as connection:
        return len(AssignmentRepository(connection).list_by_project(project_id))


def _create_project(client: TestClient, source: Path, *, page_count: int = 2) -> int:
    response = client.post(
        "/projects",
        data={
            "name": "Distribution",
            "page_count": str(page_count),
            "start_date": "2027-01-04",
            "layout_key": "two_columns",
            "source_path": str(source),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(urlsplit(response.headers["location"]).path.split("/")[-1])


def _digest(html: str) -> str:
    match = re.search(r'name="proposal_digest" value="([0-9a-f]+)"', html)
    assert match is not None
    return match.group(1)


def test_preview_shows_samples_counts_and_empty_slots(client, tmp_path):
    source = tmp_path / "photos"
    for index in range(3):
        _write_photo(source / f"p{index}.jpg", (index * 60, 0, 0))
    project_id = _create_project(client, source)

    response = client.get(f"/projects/{project_id}/distribute/preview?strategy=equal")

    assert response.status_code == 200
    assert "Distribution preview" in response.text
    assert "/media/photos/" in response.text
    assert "2 of 2 slots filled" in response.text
    assert "1 of 2 slots filled" in response.text
    assert "1 empty" in response.text
    assert "Apply distribution" in response.text
    assert _assignment_count(project_id) == 0


def test_preview_reports_overflow(client, tmp_path):
    source = tmp_path / "photos"
    for index in range(5):
        _write_photo(source / f"p{index}.jpg", (index * 50, 0, 0))
    project_id = _create_project(client, source)

    response = client.get(f"/projects/{project_id}/distribute/preview?strategy=equal")

    assert response.status_code == 200
    assert "1 photo(s) exceed the available slots" in response.text
    assert _assignment_count(project_id) == 0


def test_preview_accepts_empty_seed_from_the_form(client, tmp_path):
    source = tmp_path / "photos"
    _write_photo(source / "p0.jpg")
    project_id = _create_project(client, source)

    response = client.get(f"/projects/{project_id}/distribute/preview?strategy=equal&seed=")

    assert response.status_code == 200
    assert "Distribution preview" in response.text
    assert _assignment_count(project_id) == 0

    invalid = client.get(f"/projects/{project_id}/distribute/preview?strategy=random&seed=abc")

    assert invalid.status_code == 200
    assert "Random seed must be a whole number." in invalid.text


def test_regeneration_is_reproducible_and_does_not_save(client, tmp_path):
    source = tmp_path / "photos"
    for index in range(4):
        _write_photo(source / f"p{index}.jpg", (index * 50, 0, 0))
    project_id = _create_project(client, source)

    first = client.get(f"/projects/{project_id}/distribute/preview?strategy=random&seed=42")
    second = client.get(f"/projects/{project_id}/distribute/preview?strategy=random&seed=42")
    other = client.get(f"/projects/{project_id}/distribute/preview?strategy=random&seed=7")

    assert _digest(first.text) == _digest(second.text)
    assert _digest(first.text) != _digest(other.text)
    assert _assignment_count(project_id) == 0


def test_confirm_applies_once_and_repeat_is_noop(client, tmp_path):
    source = tmp_path / "photos"
    for index in range(4):
        _write_photo(source / f"p{index}.jpg", (index * 50, 0, 0))
    project_id = _create_project(client, source)
    preview = client.get(f"/projects/{project_id}/distribute/preview?strategy=equal")
    digest = _digest(preview.text)

    response = client.post(
        f"/projects/{project_id}/distribute/apply",
        data={"strategy": "equal", "proposal_digest": digest},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Distribution applied." in response.text
    assert _assignment_count(project_id) == 4

    repeat = client.post(
        f"/projects/{project_id}/distribute/apply",
        data={"strategy": "equal", "proposal_digest": digest},
        headers={"HX-Request": "true"},
    )
    assert repeat.status_code == 200
    assert "already distributed" in repeat.text
    assert _assignment_count(project_id) == 4


def test_stale_preview_is_rejected(client, tmp_path):
    source = tmp_path / "photos"
    for index in range(2):
        _write_photo(source / f"p{index}.jpg", (index * 50, 0, 0))
    project_id = _create_project(client, source)

    response = client.post(
        f"/projects/{project_id}/distribute/apply",
        data={"strategy": "equal", "proposal_digest": "deadbeef"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "out of date" in response.text
    assert _assignment_count(project_id) == 0


def test_created_project_opens_first_page_in_editor(client, tmp_path):
    source = tmp_path / "photos"
    _write_photo(source / "p.jpg")
    response = client.post(
        "/projects",
        data={
            "name": "Review",
            "page_count": "2",
            "start_date": "2027-01-04",
            "layout_key": "two_columns",
            "source_path": str(source),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with _database().connect() as connection:
        project_id = connection.execute("SELECT MAX(id) FROM projects").fetchone()[0]
        first_page = PageRepository(connection).list(project_id)[0]
    assert f'data-page-id="{first_page.id}"' in response.text
    assert "page-thumb active" in response.text
    assert f'href="/projects/{project_id}/settings"' in response.text
    assert "Source directories" not in response.text
    assert "Project created." in response.text
    assert "Distribute" in response.text


def test_distribution_page_renders_preview_controls(client, tmp_path):
    source = tmp_path / "photos"
    _write_photo(source / "p.jpg")
    project_id = _create_project(client, source)

    response = client.get(f"/projects/{project_id}/distribute")

    assert response.status_code == 200
    assert "Distribute photos" in response.text
    assert "Preview distribution" in response.text
    assert "Back to project" in response.text


def test_auto_distribution_uses_target_capacity_and_generates_layout(client, tmp_path):
    source = tmp_path / "photos"
    for index in range(3):
        _write_photo(source / f"p{index}.jpg", (index * 50, 0, 0))
    response = client.post(
        "/projects",
        data={
            "name": "Auto distribution",
            "page_count": "1",
            "start_date": "2027-01-04",
            "layout_key": "auto",
            "source_path": str(source),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    project_id = int(urlsplit(response.headers["location"]).path.split("/")[-1])

    preview = client.get(f"/projects/{project_id}/distribute/preview?strategy=equal")

    assert preview.status_code == 200
    # Automatic page capacity is computed from the photo/page counts (3/1 = 3).
    assert "3 of 3 slots filled" in preview.text

    digest = _digest(preview.text)
    applied = client.post(
        f"/projects/{project_id}/distribute/apply",
        data={"strategy": "equal", "proposal_digest": digest},
        headers={"HX-Request": "true"},
    )

    assert applied.status_code == 200
    assert "Distribution applied." in applied.text
    database = _database()
    try:
        with database.connect() as connection:
            page = PageRepository(connection).list(project_id)[0]
            assert page is not None and page.layout_id is not None
            layout = LayoutRepository(connection).get_by_id(page.layout_id)
            assert layout is not None
            assert layout.key == AUTO_LAYOUT_KEY
            assert len(layout.slots) == 3
            assert len(AssignmentRepository(connection).list_by_page(page.id)) == 3
    finally:
        database.close()


def test_reset_layouts_route_switches_pages_to_auto_and_redirects(client, tmp_path):
    source = tmp_path / "photos"
    for index in range(2):
        _write_photo(source / f"p{index}.jpg", (index * 50, 0, 0))
    project_id = _create_project(client, source, page_count=2)

    response = client.post(
        f"/projects/{project_id}/layouts/reset-auto",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/projects/{project_id}?layouts=1")

    database = _database()
    try:
        with database.connect() as connection:
            pages = PageRepository(connection).list(project_id)
            assert pages
            for page in pages:
                assert page.layout_id is not None
                layout = LayoutRepository(connection).get_by_id(page.layout_id)
                assert layout is not None and layout.key == AUTO_LAYOUT_KEY
    finally:
        database.close()


def test_project_detail_shows_reset_layouts_notice(client, tmp_path):
    source = tmp_path / "photos"
    _write_photo(source / "p.jpg")
    project_id = _create_project(client, source)

    response = client.get(f"/projects/{project_id}?layouts=1")

    assert response.status_code == 200
    assert "All pages reset to the Automatic layout." in response.text
