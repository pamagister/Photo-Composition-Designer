"""Browser tests for project export, downloads and full-project previews."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image
from starlette.testclient import TestClient

from photo_composition_designer.core.helpers import mm_to_px
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.routes.export import _default_export_folder
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.distribution import DistributionService
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.repositories import (
    LayoutRepository,
    PageRepository,
)
from photo_composition_designer.project.services import ProjectService


@pytest.fixture()
def gui_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GuiSettings:
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("PCD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PCD_CACHE_DIR", str(cache_dir))
    return GuiSettings(data_dir=data_dir, cache_dir=cache_dir)


@pytest.fixture()
def client(gui_settings: GuiSettings):
    with TestClient(create_app(gui_settings)) as test_client:
        yield test_client


def _write_photo(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _seed_project(
    gui_settings: GuiSettings,
    tmp_path: Path,
    *,
    name: str = "Export",
    width: int = 100,
    height: int = 80,
    dpi: int = 100,
) -> tuple[int, Path]:
    """Create a project with two pages, two photos and one assignment per page."""
    database = WorkspaceDatabase(gui_settings.workspace_path())
    try:
        service = ProjectService(database)
        project = service.create_project(
            name=name,
            page_count=2,
            start_date=datetime(2027, 1, 4),
            output_profile={
                "size": {"width": width, "height": height, "dpi": dpi, "calendar_height": 10},
                "geo": {"use_photo_location_maps": False},
                "layout": {"margin_top": 3, "margin_bottom": 2, "margin_sides": 2, "spacing": 1},
            },
        )

        source = tmp_path / f"source-{project.id}"
        for index in range(2):
            _write_photo(source / f"p{index}.jpg", (index * 80 + 40, 0, 0))
        inventory = InventoryService(database)
        root = inventory.add_source_root(project.id, source)
        inventory.scan(project.id, source_root_id=root.id)

        with database.transaction() as connection:
            layout_repository = LayoutRepository(connection)
            page_repository = PageRepository(connection)
            slots = [
                LayoutSlot(
                    id=0,
                    layout_id=0,
                    slot_key=f"slot_{index}",
                    position=index,
                    x=index * 0.5,
                    y=0.0,
                    width=0.5,
                    height=1.0,
                    z_index=0,
                    crop_mode="cover",
                )
                for index in range(2)
            ]
            layout = layout_repository.add(f"two_columns_{project.id}", 1, "Two columns", slots)
            for page in page_repository.list(project.id):
                page_repository.set_layout(page.id, layout.id, layout.version)

        distribution = DistributionService(database)
        proposal = distribution.propose(project.id, strategy="equal")
        distribution.apply(project.id, proposal)
        return project.id, source
    finally:
        database.close()


def _first_page_id(gui_settings: GuiSettings, project_id: int) -> int:
    database = WorkspaceDatabase(gui_settings.workspace_path())
    try:
        return PageRepository(database.connect()).list(project_id)[0].id
    finally:
        database.close()


def test_export_page_shows_effective_profile_and_actions(
    client: TestClient, gui_settings: GuiSettings, tmp_path: Path
):
    project_id, _ = _seed_project(gui_settings, tmp_path)

    response = client.get(f"/projects/{project_id}/export")

    assert response.status_code == 200
    assert "Effective output settings" in response.text
    assert "100 x 80 mm" in response.text
    assert 'name="folder"' in response.text
    assert f"project_{project_id}" in response.text
    assert "Source originals are" in response.text


def test_web_export_writes_ordered_pages_and_pdf(
    client: TestClient, gui_settings: GuiSettings, tmp_path: Path
):
    project_id, _ = _seed_project(gui_settings, tmp_path)

    response = client.post(
        f"/projects/{project_id}/export",
        data={"folder": "run-one", "pdf": "1"},
    )

    assert response.status_code == 200
    assert "Exported 2 of 2 page(s)" in response.text
    assert "page_000.png" in response.text
    assert "page_001.png" in response.text
    assert "Download PDF" in response.text

    output_dir = gui_settings.export_dir() / "run-one"
    assert (output_dir / "page_000.png").is_file()
    assert (output_dir / "page_001.png").is_file()
    assert (output_dir / "output.pdf").read_bytes().startswith(b"%PDF-")
    expected_size = (mm_to_px(100, 100), mm_to_px(80, 100))
    with Image.open(output_dir / "page_000.png") as page:
        assert page.size == expected_size
    with Image.open(output_dir / "page_001.png") as page:
        assert page.size == expected_size

    page_response = client.get(
        f"/projects/{project_id}/export/files?folder=run-one&name=page_000.png"
    )
    assert page_response.status_code == 200
    assert page_response.headers["content-type"] == "image/png"
    pdf_response = client.get(f"/projects/{project_id}/export/files?folder=run-one&name=output.pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"


def test_web_export_reports_missing_assets(
    client: TestClient, gui_settings: GuiSettings, tmp_path: Path
):
    project_id, source = _seed_project(gui_settings, tmp_path)
    (source / "p0.jpg").unlink()

    response = client.post(
        f"/projects/{project_id}/export",
        data={"folder": "missing", "pdf": ""},
    )

    assert response.status_code == 200
    assert "Warnings" in response.text
    assert "p0.jpg is missing at" in response.text
    assert "Exported 2 of 2 page(s)" in response.text


def test_web_export_rejects_traversal_and_accepts_absolute_destination(
    client: TestClient, gui_settings: GuiSettings, tmp_path: Path
):
    project_id, _ = _seed_project(gui_settings, tmp_path)

    response = client.post(
        f"/projects/{project_id}/export",
        data={"folder": "../escape", "pdf": ""},
    )

    assert response.status_code == 400
    assert "relative path inside the export directory" in response.text
    assert not (gui_settings.cache_dir / "escape").exists()

    response = client.post(
        f"/projects/{project_id}/export",
        data={"folder": str(tmp_path / "absolute"), "pdf": ""},
    )
    assert response.status_code == 200
    assert "Exported 2 of 2 page(s)" in response.text
    assert (tmp_path / "absolute" / "page_000.png").is_file()
    download = client.get(
        f"/projects/{project_id}/export/files",
        params={"folder": str(tmp_path / "absolute"), "name": "page_000.png"},
    )
    assert download.status_code == 200


def test_export_uses_each_project_profile(
    client: TestClient, gui_settings: GuiSettings, tmp_path: Path
):
    first_id, _ = _seed_project(gui_settings, tmp_path, name="First", width=100)
    second_id, _ = _seed_project(gui_settings, tmp_path, name="Second", width=120)

    for project_id, folder in ((first_id, "first"), (second_id, "second")):
        response = client.post(
            f"/projects/{project_id}/export",
            data={"folder": folder, "pdf": ""},
        )
        assert response.status_code == 200
        assert "Exported 2 of 2 page(s)" in response.text

    with Image.open(gui_settings.export_dir() / "first" / "page_000.png") as first_page:
        assert first_page.width == mm_to_px(100, 100)
    with Image.open(gui_settings.export_dir() / "second" / "page_000.png") as second_page:
        assert second_page.width == mm_to_px(120, 100)


def test_export_defaults_to_os_pictures_directory(
    gui_settings: GuiSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    home = tmp_path / "home"
    pictures = home / "Pictures"
    pictures.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    assert _default_export_folder(gui_settings, 12) == (
        pictures / "Photo-Composition-Designer" / "project_12"
    )


def test_preview_route_renders_pages_in_project_order(
    client: TestClient, gui_settings: GuiSettings, tmp_path: Path
):
    project_id, _ = _seed_project(gui_settings, tmp_path)
    first_page_id = _first_page_id(gui_settings, project_id)

    response = client.get(f"/projects/{project_id}/preview", follow_redirects=False)

    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert location.path == f"/projects/{project_id}"
    query = parse_qs(location.query)
    assert query["page"] == [str(first_page_id)]
    assert query["previewed"] == ["1"]

    response = client.get(response.headers["location"])
    assert response.status_code == 200
    assert "Page previews refreshed." in response.text
    previews = list((gui_settings.preview_dir() / "pages").glob("*.jpg"))
    assert len(previews) == 2
