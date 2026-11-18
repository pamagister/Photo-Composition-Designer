"""Tests for the local FastAPI web application and project workflow."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from typer.testing import CliRunner

from photo_composition_designer.cli.app import app as cli_app
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings


@pytest.fixture
def gui_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("PCD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PCD_CACHE_DIR", str(cache_dir))
    return GuiSettings(data_dir=data_dir, cache_dir=cache_dir)


@pytest.fixture
def client(gui_settings):
    with TestClient(create_app(gui_settings)) as test_client:
        yield test_client


@pytest.fixture
def source_dir(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    image = Image.new("RGB", (40, 30), "red")
    image.save(source / "photo.jpg", format="JPEG")
    return source


def _create_project(client: TestClient, *, name: str = "Family Calendar") -> str:
    response = client.post(
        "/projects",
        data={"name": name, "page_count": "2", "start_date": "2027-01-04"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"]


def test_health_and_index(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "photo-composition-designer",
        "schema_version": 1,
    }

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/projects"

    response = client.get("/static/style.css")
    assert response.status_code == 200


def test_create_open_and_rename_project(client):
    project_url = _create_project(client)

    response = client.get(project_url)
    assert response.status_code == 200
    assert "Family Calendar" in response.text
    assert "No source directory configured" in response.text

    response = client.post(
        f"{project_url}/rename",
        data={"name": "Renamed Calendar"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "saved=1" in response.headers["location"]

    response = client.get(response.headers["location"])
    assert response.status_code == 200
    assert "Renamed Calendar" in response.text
    assert "Project name saved." in response.text


def test_create_project_rejects_invalid_input(client):
    response = client.post(
        "/projects",
        data={"name": " ", "page_count": "0", "start_date": "2027-01-04"},
    )

    assert response.status_code == 400
    assert "project name must not be empty" in response.text


def test_scan_inventory_and_media(client, source_dir):
    project_url = _create_project(client)
    response = client.post(
        f"{project_url}/source",
        data={"path": str(source_dir)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "added=1" in response.headers["location"]

    response = client.post(
        f"{project_url}/scan",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "1 photos found" in response.text
    assert "/media/photos/" in response.text

    inventory = client.get(f"{project_url}/inventory")
    assert inventory.status_code == 200
    match = re.search(r"/media/photos/(\d+)", inventory.text)
    assert match is not None
    photo_id = match.group(1)

    thumbnail = client.get(f"/media/photos/{photo_id}")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/jpeg"
    assert "max-age=86400" in thumbnail.headers["cache-control"]

    original = client.get(f"/media/photos/{photo_id}/original")
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/jpeg"


def test_missing_source_is_reported(client, tmp_path):
    project_url = _create_project(client)
    missing = tmp_path / "does-not-exist"

    response = client.post(
        f"{project_url}/source",
        data={"path": str(missing)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=" in response.headers["location"]


def test_rescanning_marks_deleted_photos_unavailable(client, source_dir):
    project_url = _create_project(client)
    client.post(f"{project_url}/source", data={"path": str(source_dir)})
    client.post(f"{project_url}/scan", headers={"HX-Request": "true"})

    inventory = client.get(f"{project_url}/inventory")
    match = re.search(r"/media/photos/(\d+)", inventory.text)
    assert match is not None
    photo_id = match.group(1)

    (source_dir / "photo.jpg").unlink()
    response = client.post(f"{project_url}/scan", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "1 unavailable" in response.text
    assert client.get(f"/media/photos/{photo_id}").status_code == 404


def test_browse_directories(client, source_dir):
    response = client.get("/api/browse", params={"path": str(source_dir)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == str(source_dir)
    assert payload["directories"] == []


def test_browse_rejects_missing_directory(client, tmp_path):
    response = client.get("/api/browse", params={"path": str(tmp_path / "missing")})

    assert response.status_code == 400
    assert response.json()["detail"] == "not a directory"


def test_cli_exposes_gui_command():
    result = CliRunner().invoke(cli_app, ["--help"])

    assert result.exit_code == 0
    assert "gui" in result.stdout
    assert "Start the local web editor" in result.stdout
