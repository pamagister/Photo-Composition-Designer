"""Tests for browser source management, remapping and reliability."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

import pytest
from PIL import Image
from starlette.testclient import TestClient

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PhotoRepository,
    SourceRootRepository,
)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    return TestClient(create_app(GuiSettings()))


def _write_photo(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _database() -> WorkspaceDatabase:
    return WorkspaceDatabase(data_dir() / "workspace.sqlite3")


def _create_project(
    client: TestClient,
    *,
    page_count: int = 1,
    layout_key: str = "single_full",
) -> int:
    response = client.post(
        "/projects",
        data={
            "name": "Sources",
            "page_count": str(page_count),
            "start_date": "2027-01-04",
            "layout_key": layout_key,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(response.headers["location"].split("/")[-1])


def _add_source(client: TestClient, project_id: int, path: Path) -> None:
    response = client.post(
        f"/projects/{project_id}/source",
        data={"path": str(path)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "added=1" in response.headers["location"]


def _scan(client: TestClient, project_id: int) -> str:
    response = client.post(
        f"/projects/{project_id}/scan",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    return response.text


def _source_root(project_id: int, *, active: bool | None = None):
    with _database().connect() as connection:
        repository = SourceRootRepository(connection)
        if active is None:
            roots = repository.list(project_id)
            assert roots
            return roots[0]
        if active:
            root = repository.get_active(project_id)
        else:
            root = next(root for root in repository.list(project_id) if not root.active)
        assert root is not None
        return root


def test_remap_preview_reports_ambiguity_without_mutation(client, tmp_path):
    project_id = _create_project(client, page_count=2)
    old = tmp_path / "old"
    _write_photo(old / "a.jpg")
    _write_photo(old / "b.jpg")
    _add_source(client, project_id, old)
    _scan(client, project_id)

    new = tmp_path / "new"
    _write_photo(new / "a.jpg")
    _write_photo(new / "one" / "b.jpg")
    _write_photo(new / "two" / "b.jpg")
    root = _source_root(project_id)

    response = client.get(
        f"/projects/{project_id}/source/{root.id}/remap/preview",
        params={"new_root": str(new)},
    )

    assert response.status_code == 200
    assert "1 of 2" in response.text
    assert "b.jpg" in response.text
    assert "ambiguous basename" in response.text
    assert "Existing assignments are preserved." in response.text

    with _database().connect() as connection:
        unchanged = SourceRootRepository(connection).get(root.id)
        photos = PhotoRepository(connection).list(project_id)
    assert unchanged is not None
    assert unchanged.path == str(old.resolve())
    assert len(photos) == 2


def test_remap_apply_relinks_and_preserves_assignments(client, tmp_path):
    project_id = _create_project(client)
    old = tmp_path / "old"
    _write_photo(old / "a.jpg")
    _add_source(client, project_id, old)
    _scan(client, project_id)
    response = client.post(
        f"/projects/{project_id}/distribute/apply",
        data={"strategy": "equal"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    new = tmp_path / "new"
    _write_photo(new / "nested" / "a.jpg")
    root = _source_root(project_id)

    response = client.post(
        f"/projects/{project_id}/source/{root.id}/remap",
        data={"new_root": str(new)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "remapped=1" in response.headers["location"]
    with _database().connect() as connection:
        updated = SourceRootRepository(connection).get(root.id)
        photos = PhotoRepository(connection).list(project_id)
        assignments = AssignmentRepository(connection).list_by_project(project_id)
    assert updated is not None
    assert updated.path == str(new.resolve())
    assert [photo.relative_path for photo in photos] == ["nested/a.jpg"]
    assert photos[0].available
    assert len(assignments) == 1


def test_missing_files_stay_visible_and_assigned(client, tmp_path):
    project_id = _create_project(client)
    source = tmp_path / "source"
    _write_photo(source / "a.jpg")
    _add_source(client, project_id, source)
    _scan(client, project_id)
    response = client.post(
        f"/projects/{project_id}/distribute/apply",
        data={"strategy": "equal"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    (source / "a.jpg").unlink()

    text = _scan(client, project_id)

    assert "0 photos found" in text
    assert "1 unavailable" in text
    assert "Symbolic links are skipped." in text

    inventory = client.get(f"/projects/{project_id}/inventory")
    assert inventory.status_code == 200
    assert "missing" in inventory.text
    assert "assigned" in inventory.text
    assert 'aria-label="a.jpg is missing"' in inventory.text

    with _database().connect() as connection:
        assignments = AssignmentRepository(connection).list_by_project(project_id)
    assert len(assignments) == 1


def test_source_switch_duplicate_and_remove(client, tmp_path):
    project_id = _create_project(client)
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_photo(first / "a.jpg")
    _write_photo(second / "b.jpg")
    _add_source(client, project_id, first)
    _scan(client, project_id)
    _add_source(client, project_id, second)

    active = _source_root(project_id, active=True)
    assert active.path == str(second.resolve())
    text = _scan(client, project_id)
    assert "1 photos found" in text

    renewed = client.post(
        f"/projects/{project_id}/source",
        data={"path": str(first)},
        follow_redirects=False,
    )
    assert renewed.status_code == 303
    assert "already%20configured" in renewed.headers["location"]

    old_root = _source_root(project_id, active=False)
    activated = client.post(
        f"/projects/{project_id}/source/{old_root.id}/activate",
        follow_redirects=False,
    )
    assert activated.status_code == 303
    assert "activated=1" in activated.headers["location"]
    assert _source_root(project_id, active=True).id == old_root.id

    removed = client.post(
        f"/projects/{project_id}/source/{active.id}/remove",
        follow_redirects=False,
    )
    assert removed.status_code == 303
    assert "removed=1" in removed.headers["location"]
    with _database().connect() as connection:
        remaining = SourceRootRepository(connection).list(project_id)
    assert [root.id for root in remaining] == [old_root.id]


def test_removing_a_root_with_assigned_photos_is_refused(client, tmp_path):
    project_id = _create_project(client)
    source = tmp_path / "source"
    _write_photo(source / "a.jpg")
    _add_source(client, project_id, source)
    _scan(client, project_id)
    response = client.post(
        f"/projects/{project_id}/distribute/apply",
        data={"strategy": "equal"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    root = _source_root(project_id)

    response = client.post(
        f"/projects/{project_id}/source/{root.id}/remove",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "unassign" in unquote(response.headers["location"])
    with _database().connect() as connection:
        assert SourceRootRepository(connection).get(root.id) is not None
        assert len(AssignmentRepository(connection).list_by_project(project_id)) == 1
