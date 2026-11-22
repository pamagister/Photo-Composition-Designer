"""Tests for the immutable preview asset route (plan Phase 2).

The asset route serves cached previews by their content-derived cache key
without consulting mutable page state. Because the URL identifies the exact
cached bytes, the response can be cached forever: a new revision produces a
new key and therefore a new URL.

These tests guard the contract:

* the asset route serves with ``Cache-Control: public, max-age=...,
  immutable``;
* the route never renders on a miss (returns 404 when the file is absent);
* an in-flight old revision's URL still serves the original complete bytes
  after a new revision is rendered.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image
from starlette.testclient import TestClient

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.repositories import PageRepository
from photo_composition_designer.project.services import ProjectService


def _write_photo(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _seed(tmp_path: Path, *, page_count: int = 1) -> tuple[int, int]:
    """Seed a workspace with a project and one page; return (project_id, page_id)."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        project = ProjectService(database).create_project(
            name="Asset",
            page_count=page_count,
            start_date=datetime(2027, 1, 4),
        )
        source = tmp_path / "asset-source"
        for index in range(4):
            _write_photo(source / f"photo_{index:02d}.jpg", (index * 50, 0, 0))
        inventory = InventoryService(database)
        root = inventory.add_source_root(project.id, source)
        inventory.scan(project.id, source_root_id=root.id)
        with database.connect() as connection:
            page = PageRepository(connection).list(project.id)[0]
        return project.id, page.id
    finally:
        database.close()


def _cache_key(
    tmp_path: Path,
    project_id: int,
    page_id: int,
    *,
    max_width: int = 200,
) -> str:
    """Compute the preview cache key for a page using the same inputs the renderer uses."""
    from photo_composition_designer.project.rendering import (
        ProjectRenderingService,
        preview_cache_key_for,
    )

    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        rendering = ProjectRenderingService(database)
        connection = database.connect()
        page = PageRepository(connection).get(page_id)
        assert page is not None
        return preview_cache_key_for(rendering, connection, page, max_width=max_width)
    finally:
        connection.close()
        database.close()


def test_preview_asset_serves_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, page_id = _seed(tmp_path)

    # Render the preview to create the file on disk.
    rendered = client.get(
        f"/projects/{project_id}/pages/{page_id}/preview", params={"max_width": 200}
    )
    assert rendered.status_code == 200
    assert rendered.headers["cache-control"] == "no-cache"

    # The immutable asset route serves the same bytes with a long-lived cache.
    key = _cache_key(tmp_path, project_id, page_id, max_width=200)
    asset = client.get(f"/projects/{project_id}/preview-assets/{key}.jpg")
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "image/jpeg"
    assert "immutable" in asset.headers["cache-control"]
    assert "max-age=31536000" in asset.headers["cache-control"]
    assert asset.content == rendered.content


def test_preview_asset_returns_404_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, page_id = _seed(tmp_path)

    # No preview has been rendered yet, so the asset route must not render.
    key = _cache_key(tmp_path, project_id, page_id, max_width=200)
    response = client.get(f"/projects/{project_id}/preview-assets/{key}.jpg")
    assert response.status_code == 404


def test_preview_asset_rejects_invalid_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, _ = _seed(tmp_path)

    # A path-traversal attempt must be rejected before touching the filesystem.
    response = client.get(f"/projects/{project_id}/preview-assets/../../etc/passwd.jpg")
    assert response.status_code == 404
    response = client.get(f"/projects/{project_id}/preview-assets/NOTAHEXKEY123456789012.jpg")
    assert response.status_code == 400


def test_preview_asset_old_revision_serves_original_bytes(tmp_path, monkeypatch):
    """An in-flight request for an old revision's URL must still serve the
    original complete bytes after a new revision is rendered."""
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, page_id = _seed(tmp_path)

    # Render the preview at the initial revision.
    client.get(f"/projects/{project_id}/pages/{page_id}/preview", params={"max_width": 200})
    old_key = _cache_key(tmp_path, project_id, page_id, max_width=200)
    old_bytes = client.get(f"/projects/{project_id}/preview-assets/{old_key}.jpg").content

    # Change the page (assign a photo) to bump the revision.
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        with database.connect() as connection:
            photo_id = connection.execute("SELECT id FROM photos ORDER BY id LIMIT 1").fetchone()[0]
            layout = connection.execute(
                "SELECT layout_id FROM pages WHERE id = ?", (page_id,)
            ).fetchone()
            slot_id = None
            if layout and layout[0] is not None:
                slot = connection.execute(
                    "SELECT id FROM layout_slots WHERE layout_id = ? ORDER BY position LIMIT 1",
                    (layout[0],),
                ).fetchone()
                slot_id = slot[0] if slot else None
    finally:
        database.close()

    if slot_id is not None:
        assign = client.post(
            f"/projects/{project_id}/pages/{page_id}/assign",
            data={"slot_id": slot_id, "photo_id": photo_id},
        )
        assert assign.status_code == 200

        # Render the preview at the new revision.
        client.get(f"/projects/{project_id}/pages/{page_id}/preview", params={"max_width": 200})
        new_key = _cache_key(tmp_path, project_id, page_id, max_width=200)
        assert new_key != old_key

        # The old asset URL still serves the original complete bytes.
        old_response = client.get(f"/projects/{project_id}/preview-assets/{old_key}.jpg")
        assert old_response.status_code == 200
        assert old_response.content == old_bytes


def test_preview_status_returns_ready_when_file_exists(tmp_path, monkeypatch):
    """The status endpoint returns 'ready' when the preview file exists."""
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, page_id = _seed(tmp_path)

    # Render the preview to create the file.
    client.get(f"/projects/{project_id}/pages/{page_id}/preview", params={"max_width": 200})

    status = client.get(
        f"/projects/{project_id}/pages/{page_id}/preview-status", params={"max_width": 200}
    )
    assert status.status_code == 200
    data = status.json()
    assert data["status"] == "ready"
    assert data["revision"] >= 0


def test_preview_status_is_scoped_to_the_requested_job(tmp_path, monkeypatch):
    """A stale failure for another width must not fail the requested preview."""
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, page_id = _seed(tmp_path)

    worker = client.app.state.preview_worker
    worker._job_errors[("other", 0, 0, "preview")] = "unrelated stale failure"

    status = client.get(
        f"/projects/{project_id}/pages/{page_id}/preview-status", params={"max_width": 200}
    )
    assert status.status_code == 200
    assert status.json()["status"] in ("ready", "refreshing")


def test_preview_status_reports_only_the_failed_job(tmp_path, monkeypatch):
    """The status endpoint returns the error for the exact requested job."""
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, page_id = _seed(tmp_path)

    # The status endpoint submits the requested job, which clears its prior
    # failure. Seed the error after submission via a one-shot submit that
    # raises before the endpoint's status check.
    worker = client.app.state.preview_worker
    worker._job_errors[("unrelated", 0, 0, "preview")] = "unrelated stale failure"

    original_submit = worker.submit

    def submit_then_fail(project_id, page_id, **kwargs):
        original_submit(project_id, page_id, **kwargs)
        key = (project_id, page_id, kwargs["max_width"], kwargs.get("mode", "preview"))
        worker._job_errors[key] = "boom"

    worker.submit = submit_then_fail
    status = client.get(
        f"/projects/{project_id}/pages/{page_id}/preview-status", params={"max_width": 200}
    )
    assert status.status_code == 200
    assert status.json()["status"] == "error"
    assert status.json()["error"] == "boom"

    # A different width for the same page is not affected by the 200 failure.
    worker.submit = original_submit
    worker._job_errors.pop((project_id, page_id, 800, "preview"), None)
    other = client.get(
        f"/projects/{project_id}/pages/{page_id}/preview-status", params={"max_width": 800}
    )
    assert other.json()["status"] in ("ready", "refreshing")


def test_preview_status_returns_refreshing_or_ready_when_file_absent(tmp_path, monkeypatch):
    """The status endpoint returns 'refreshing' (or 'ready' with sync worker)
    when the file is absent."""
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, page_id = _seed(tmp_path)

    # No preview has been rendered yet.
    status = client.get(
        f"/projects/{project_id}/pages/{page_id}/preview-status", params={"max_width": 200}
    )
    assert status.status_code == 200
    data = status.json()
    # With the sync worker, the status endpoint submits a job that renders
    # inline, so by the time the response is built the file may exist.
    assert data["status"] in ("ready", "refreshing")


def test_preview_route_returns_200_with_sync_worker(tmp_path, monkeypatch):
    """The preview route returns 200 with a real image (sync worker renders
    inline, so the file exists by the time the route checks)."""
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))
    client = TestClient(create_app(GuiSettings(), sync_preview_worker=True))
    project_id, page_id = _seed(tmp_path)

    response = client.get(
        f"/projects/{project_id}/pages/{page_id}/preview", params={"max_width": 200}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert len(response.content) > 100  # Not the 1x1 placeholder
