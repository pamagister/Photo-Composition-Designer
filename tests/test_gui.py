"""Tests for the local FastAPI web application and project workflow."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from typer.testing import CliRunner

from photo_composition_designer.cli.app import app as cli_app
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings, load_gui_settings


@pytest.fixture
def gui_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("PCD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PCD_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("PCD_CONFIG_DIR", str(tmp_path / "config"))
    return GuiSettings(data_dir=data_dir, cache_dir=cache_dir)


@pytest.fixture
def client(gui_settings):
    with TestClient(create_app(gui_settings, sync_preview_worker=True)) as test_client:
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
    return urlsplit(response.headers["location"]).path


def test_health_and_index(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "photo-composition-designer",
        "schema_version": 4,
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
    assert "No photos scanned yet." in response.text

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

    inventory = client.get(f"{project_url}/inventory")
    assert "/media/photos/" in inventory.text
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


def test_global_anniversaries_setting_is_saved_and_validated(client, tmp_path):
    anniversaries = tmp_path / "anniversaries.ini"
    anniversaries.write_text("[Birthdays]\nPaul = 6.1.\n", encoding="utf-8")

    response = client.post(
        "/settings",
        data={"anniversaries_path": str(anniversaries)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/settings?saved=1").status_code == 200
    assert str(anniversaries) in client.get("/settings").text
    assert load_gui_settings().anniversaries_path == anniversaries.resolve()

    invalid = client.post(
        "/settings",
        data={"anniversaries_path": str(tmp_path / "missing.ini")},
    )
    assert invalid.status_code == 200
    assert "anniversaries file does not exist" in invalid.text
    assert str(tmp_path / "missing.ini") in invalid.text


def test_global_locations_setting_is_saved_and_validated(client, tmp_path):
    locations = tmp_path / "locations.ini"
    locations.write_text("[CUSTOM]\nWeimar = 50.9795, 11.3235\n", encoding="utf-8")

    response = client.post(
        "/settings",
        data={"locations_path": str(locations)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert str(locations) in client.get("/settings").text
    assert load_gui_settings().locations_path == locations.resolve()

    invalid = client.post(
        "/settings",
        data={"locations_path": str(tmp_path / "missing.ini")},
    )
    assert invalid.status_code == 200
    assert "locations file does not exist" in invalid.text
    assert str(tmp_path / "missing.ini") in invalid.text


def test_built_in_settings_show_the_bundled_format(client):
    anniversaries = client.get("/settings/built-in/anniversaries.ini")
    assert anniversaries.status_code == 200
    assert "[Birthdays]" in anniversaries.text

    locations = client.get("/settings/built-in/locations.ini")
    assert locations.status_code == 200
    assert "Frankfurt = 50.1109, 8.6821" in locations.text
    assert "locations_de.ini" in locations.text
    assert "locations_en.ini" in locations.text

    assert client.get("/settings/built-in/unknown.ini").status_code == 404


def test_page_overrides_persist(client):
    project_url = _create_project(client)
    project_page = client.get(project_url)
    page_ids = re.findall(r"[?&]page=(\d+)", project_page.text)
    assert page_ids
    page_id = page_ids[-1]

    response = client.post(
        f"{project_url}/pages/{page_id}/overrides",
        data={
            "hide_local_map": "1",
            "hide_calendar_strip": "1",
            "hide_description": "1",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Page overrides saved." in response.text
    assert response.text.count("checked") >= 3


def _slot_grid_columns(client: TestClient, layout_key: str) -> str | None:
    """Create a one-page project with a layout and return its grid column count."""
    response = client.post(
        "/projects",
        data={
            "name": "Tiled Calendar",
            "page_count": "1",
            "start_date": "2027-01-04",
            "layout_key": layout_key,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    project_page = client.get(urlsplit(response.headers["location"]).path)
    assert project_page.status_code == 200
    match = re.search(r"--slot-columns:\s*(\d+);", project_page.text)
    return match.group(1) if match else None


def test_slot_grid_caps_columns_at_three(client):
    # A five-slot layout would render every slot in one row without the cap.
    assert _slot_grid_columns(client, "five_two_three") == "3"
    # Two-slot layouts are unaffected.
    assert _slot_grid_columns(client, "two_columns") == "2"


def test_populate_button_shows_when_slots_are_empty(client):
    response = client.post(
        "/projects",
        data={
            "name": "Fill Calendar",
            "page_count": "1",
            "start_date": "2027-01-04",
            "layout_key": "five_two_three",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    project_page = client.get(urlsplit(response.headers["location"]).path)
    assert project_page.status_code == 200
    assert "Fill empty slots with unused photos" in project_page.text


def test_unused_pool_renders_selection_checkbox_and_toolbar(client, source_dir):
    response = client.post(
        "/projects",
        data={
            "name": "Multi Select",
            "page_count": "1",
            "start_date": "2027-01-04",
            "layout_key": "five_two_three",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    project_path = urlsplit(response.headers["location"]).path
    client.post(
        f"{project_path}/source",
        data={"path": str(source_dir)},
        follow_redirects=False,
    )
    client.post(f"{project_path}/scan", headers={"HX-Request": "true"})

    page = client.get(project_path)
    assert page.status_code == 200
    assert "photo-select-toolbar" in page.text
    assert "Assign selected" in page.text
    assert "unused-item-checkbox" in page.text
    assert 'value="unused"' in page.text or "selected" in page.text


def test_global_layout_editor_saves_new_versions(client):
    layout_data = """[
      {"key":"left","x":0,"y":0,"width":0.5,"height":1},
      {"key":"right","x":0.5,"y":0,"width":0.5,"height":1}
    ]"""
    response = client.post(
        "/layouts",
        data={"key": "test_layout", "name": "Test Layout", "slots_json": layout_data},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "key=test_layout" in response.headers["location"]

    editor = client.get("/layouts?key=test_layout")
    assert editor.status_code == 200
    assert "Test Layout" in editor.text
    assert "test_layout v1" in editor.text

    response = client.post(
        "/layouts",
        data={
            "key": "test_layout",
            "name": "Test Layout Updated",
            "slots_json": layout_data,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    layouts = client.get("/layouts?key=test_layout&saved=1")
    assert "test_layout v2" in layouts.text
    assert "Layout version saved." in layouts.text


def test_pcd_project_export_and_import(client):
    project_url = _create_project(client, name="Archive Calendar")

    exported = client.get(f"{project_url}/archive")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/vnd.photo-composition-designer"
    assert "filename*=UTF-8''Archive%20Calendar.pcd" in exported.headers["content-disposition"]

    imported = client.post(
        "/projects/import-pcd",
        files={
            "archive": (
                "calendar.pcd",
                exported.content,
                "application/vnd.photo-composition-designer",
            )
        },
        follow_redirects=False,
    )
    assert imported.status_code == 303
    assert imported.headers["location"] != project_url
    assert client.get(imported.headers["location"]).status_code == 200


def test_cli_exposes_gui_command():
    result = CliRunner().invoke(cli_app, ["--help"])

    assert result.exit_code == 0
    assert "gui" in result.stdout
    assert "Start the local web editor" in result.stdout


def test_object_detection_settings_are_saved(client, tmp_path):
    model = tmp_path / "yolo26n.onnx"
    model.write_bytes(b"fake-model")

    response = client.post(
        "/settings",
        data={"object_detection_enabled": "1", "yolo_model_path": str(model)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    settings = load_gui_settings()
    assert settings.object_detection_enabled is True
    assert settings.yolo_model_path == model.resolve()
    assert "Model file found." in client.get("/settings").text


def test_object_detection_defaults_to_disabled(client):
    assert load_gui_settings().object_detection_enabled is False


def test_yolo_download_writes_default_model(client, monkeypatch):
    from photo_composition_designer.gui.routes import app_settings as route

    def fake_download(destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"model-bytes")

    monkeypatch.setattr(route, "_download_yolo_model", fake_download)

    response = client.post("/settings/yolo/download", follow_redirects=False)

    assert response.status_code == 303
    settings = load_gui_settings()
    assert settings.yolo_model_path is not None
    assert settings.yolo_model_path.is_file()
    assert settings.yolo_model_path.read_bytes() == b"model-bytes"


def test_download_yolo_model_streams_to_disk(tmp_path, monkeypatch):
    from photo_composition_designer.gui.routes import app_settings as route

    class FakeResponse:
        def __init__(self, data):
            self._data = data
            self._sent = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            if self._sent:
                return b""
            self._sent = True
            return self._data

    monkeypatch.setattr(
        route.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse(b"model-bytes")
    )
    destination = tmp_path / "nested" / "yolo26n.onnx"

    route._download_yolo_model(destination)

    assert destination.read_bytes() == b"model-bytes"


def test_yolo_download_reports_network_errors(client, monkeypatch):
    from photo_composition_designer.gui.routes import app_settings as route

    def fail(*args, **kwargs):
        raise OSError("network unreachable")

    monkeypatch.setattr(route, "_download_yolo_model", fail)

    response = client.post("/settings/yolo/download", follow_redirects=False)

    assert response.status_code == 303
    assert "error=" in response.headers["location"]


def test_yolo_test_reports_missing_model(client):
    response = client.post("/settings/yolo/test", follow_redirects=False)

    assert response.status_code == 303
    assert "error=" in response.headers["location"]


def test_build_object_detector_returns_none_when_unavailable(tmp_path):
    from photo_composition_designer.render.object_detector import build_object_detector

    missing = tmp_path / "missing.onnx"

    assert build_object_detector(enabled=False, model_path=missing) is None
    assert build_object_detector(enabled=True, model_path=None) is None
    assert build_object_detector(enabled=True, model_path=missing) is None


def test_check_page_is_under_construction(client):
    project_url = _create_project(client)
    project_id = urlsplit(project_url).path.split("/")[-1]

    response = client.get(f"/projects/{project_id}/check")

    assert response.status_code == 200
    assert "Under construction." in response.text
    assert "Back to project" in response.text
