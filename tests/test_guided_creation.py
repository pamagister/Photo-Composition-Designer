"""Tests for guided project creation, distribution preview and rendering."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import pytest
from PIL import Image
from starlette.testclient import TestClient

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.repositories import (
    LayoutRepository,
    PageRepository,
)


@pytest.fixture()
def guided_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    app = create_app(GuiSettings(), sync_preview_worker=True)
    return TestClient(app)


def _write_photo(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def test_new_project_form_shows_layout_catalogue(guided_client):
    response = guided_client.get("/projects/new")
    assert response.status_code == 200
    assert "layout_key" in response.text
    assert "single_full" in response.text or "Single full" in response.text


def test_create_project_with_layout_assigns_slots(guided_client, tmp_path):
    response = guided_client.post(
        "/projects",
        data={
            "name": "Guided",
            "page_count": 1,
            "start_date": "2027-01-04",
            "layout_key": "two_columns",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    project_id = int(urlsplit(response.headers["location"]).path.split("/")[-1])

    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    with database.connect() as connection:
        pages = PageRepository(connection).list(project_id)
        assert pages[0].layout_id is not None
        layout = LayoutRepository(connection).get_by_id(pages[0].layout_id)
        assert len(layout.slots) == 2


def test_create_project_with_source_scans(guided_client, tmp_path):
    source = tmp_path / "photos"
    _write_photo(source / "a.jpg")
    response = guided_client.post(
        "/projects",
        data={
            "name": "WithSource",
            "page_count": 1,
            "start_date": "2027-01-04",
            "layout_key": "single_full",
            "source_path": str(source),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    project_id = int(urlsplit(response.headers["location"]).path.split("/")[-1])

    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM photos WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
    assert count == 1


def test_distribution_preview_does_not_mutate(guided_client, tmp_path):
    source = tmp_path / "photos"
    for i in range(4):
        _write_photo(source / f"p{i}.jpg", (i * 40, 0, 0))
    guided_client.post(
        "/projects",
        data={
            "name": "Preview",
            "page_count": 2,
            "start_date": "2027-01-04",
            "layout_key": "two_columns",
            "source_path": str(source),
        },
        follow_redirects=False,
    )
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    with database.connect() as connection:
        project_id = connection.execute(
            "SELECT id FROM projects ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]

    response = guided_client.get(f"/projects/{project_id}/distribute/preview?strategy=equal")
    assert response.status_code == 200
    assert "Distribution preview" in response.text

    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    assert count == 0


def test_apply_distribution_persists_assignments(guided_client, tmp_path):
    source = tmp_path / "photos"
    for i in range(4):
        _write_photo(source / f"p{i}.jpg", (i * 40, 0, 0))
    guided_client.post(
        "/projects",
        data={
            "name": "Apply",
            "page_count": 2,
            "start_date": "2027-01-04",
            "layout_key": "two_columns",
            "source_path": str(source),
        },
        follow_redirects=False,
    )
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    with database.connect() as connection:
        project_id = connection.execute(
            "SELECT id FROM projects ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]

    response = guided_client.post(
        f"/projects/{project_id}/distribute/apply",
        data={"strategy": "equal"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    assert count == 4
