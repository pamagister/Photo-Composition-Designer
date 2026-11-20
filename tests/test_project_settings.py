"""Browser tests for per-project output settings and project duplication."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import pytest
from starlette.testclient import TestClient

from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.gui.app import create_app
from photo_composition_designer.gui.settings import GuiSettings
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.repositories import (
    LayoutRepository,
    PageRepository,
    ProjectRepository,
)


@pytest.fixture()
def gui_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GuiSettings:
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("PCD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PCD_CACHE_DIR", str(cache_dir))
    return GuiSettings(data_dir=data_dir, cache_dir=cache_dir)


@pytest.fixture()
def client(gui_settings: GuiSettings):
    with TestClient(create_app(gui_settings, sync_preview_worker=True)) as test_client:
        yield test_client


def _create_project(client: TestClient, *, name: str = "Family Calendar") -> int:
    response = client.post(
        "/projects",
        data={"name": name, "page_count": "2", "start_date": "2027-01-04"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return int(urlsplit(response.headers["location"]).path.split("/")[-1])


def _settings_form(**overrides: str) -> dict[str, str]:
    """Return a complete valid settings submission."""
    profile = OutputProfile.default()
    form = {
        "calendar.use_calendar": "1" if profile.calendar.use_calendar else "",
        "calendar.language": profile.calendar.language,
        "calendar.holiday_countries": ",".join(profile.calendar.holiday_countries),
        "calendar.title": profile.calendar.title,
        "calendar.horizontal_orientation": ("1" if profile.calendar.horizontal_orientation else ""),
        "calendar.use_short_day_names": ("1" if profile.calendar.use_short_day_names else ""),
        "calendar.use_short_month_names": ("1" if profile.calendar.use_short_month_names else ""),
        "calendar.use_title_page": ("1" if profile.calendar.use_title_page else ""),
        "style.background_color": profile.style.background_color,
        "style.font_large.name": profile.style.font_large.name,
        "style.font_large.size": str(profile.style.font_large.size),
        "style.font_large.color": profile.style.font_large.color,
        "style.font_small.name": profile.style.font_small.name,
        "style.font_small.size": str(profile.style.font_small.size),
        "style.font_small.color": profile.style.font_small.color,
        "style.font_description.name": profile.style.font_description.name,
        "style.font_description.size": str(profile.style.font_description.size),
        "style.font_description.color": profile.style.font_description.color,
        "style.font_anniversaries.name": profile.style.font_anniversaries.name,
        "style.font_anniversaries.size": str(profile.style.font_anniversaries.size),
        "style.font_anniversaries.color": profile.style.font_anniversaries.color,
        "geo.use_photo_location_maps": "1" if profile.geo.use_photo_location_maps else "",
        "geo.minimal_extension": str(profile.geo.minimal_extension),
        "geo.map_size": str(profile.geo.map_size),
        "size.width": str(profile.size.width),
        "size.height": str(profile.size.height),
        "size.calendar_height": str(profile.size.calendar_height),
        "size.dpi": str(profile.size.dpi),
        "size.jpeg_quality": str(profile.size.jpeg_quality),
        "layout.margin_top": str(profile.layout.margin_top),
        "layout.margin_bottom": str(profile.layout.margin_bottom),
        "layout.margin_sides": str(profile.layout.margin_sides),
        "layout.spacing": str(profile.layout.spacing),
        "layout.use_rounded_corners": ("1" if profile.layout.use_rounded_corners else ""),
        "layout.image_score_factor": str(profile.layout.image_score_factor),
        "layout.use_photo_description": ("1" if profile.layout.use_photo_description else ""),
    }
    form.update(overrides)
    return form


def _database(gui_settings: GuiSettings) -> WorkspaceDatabase:
    return WorkspaceDatabase(gui_settings.workspace_path())


def _project_state(gui_settings: GuiSettings, project_id: int):
    with _database(gui_settings).connect() as connection:
        project = ProjectRepository(connection).get(project_id)
        pages = PageRepository(connection).list(project_id)
    assert project is not None
    return project, pages


def test_settings_page_shows_current_profile(client: TestClient):
    project_id = _create_project(client)

    response = client.get(f"/projects/{project_id}/settings")

    assert response.status_code == 200
    assert "Project settings" in response.text
    assert 'name="size.dpi"' in response.text
    assert 'value="300"' in response.text
    assert 'name="layout.generate_pdf"' not in response.text
    assert "Duplicate project" not in response.text


def test_project_detail_shows_extras_and_check_sections(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    response = client.get(f"/projects/{project_id}")

    assert response.status_code == 200
    assert "Extras" in response.text
    assert f'href="/projects/{project_id}/distribute"' in response.text
    assert f'href="/projects/{project_id}/check"' in response.text


def test_global_navigation_shows_project_actions_only_for_open_project(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    detail = client.get(f"/projects/{project_id}")

    assert detail.status_code == 200
    assert 'href="/projects"' in detail.text
    assert 'href="/settings"' in detail.text
    assert 'href="/layouts"' in detail.text
    assert f'href="/projects/{project_id}/settings"' in detail.text
    assert f'href="/projects/{project_id}/preview' in detail.text
    assert f'href="/projects/{project_id}/distribute"' in detail.text
    assert f'href="/projects/{project_id}/check"' in detail.text
    assert f'href="/projects/{project_id}/export"' in detail.text
    assert 'href="https://photo-composition-designer.readthedocs.io/en/stable/"' in detail.text
    assert 'target="_blank"' in detail.text
    assert 'rel="noopener noreferrer"' in detail.text
    assert ">PCD</a>" not in detail.text

    overview = client.get("/projects")

    assert overview.status_code == 200
    assert f'href="/projects/{project_id}/settings"' not in overview.text
    assert f'href="/projects/{project_id}/preview"' not in overview.text
    assert f'href="/projects/{project_id}/export"' not in overview.text
    assert ">Extras" not in overview.text


def test_projects_page_exposes_archive_import_and_duplicate_controls(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    projects = client.get("/projects")

    assert projects.status_code == 200
    assert f'href="/projects/{project_id}/archive"' in projects.text
    assert "Export project (.pcd)" in projects.text
    assert "Duplicate project" in projects.text
    assert 'action="/projects/import-pcd"' in projects.text
    assert "Import project (.pcd)" in projects.text


def test_project_detail_no_longer_duplicates_archive_or_imports(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    detail = client.get(f"/projects/{project_id}")

    assert detail.status_code == 200
    assert "Export project (.pcd)" not in detail.text
    assert "Import project (.pcd)" not in detail.text
    assert "Duplicate project" not in detail.text


def test_settings_save_persists_profile_and_invalidates_pages(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(
            **{
                "calendar.language": "en_US",
                "calendar.holiday_countries": "SN, DE",
                "size.dpi": "150",
                "style.background_color": "#000000",
            }
        ),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("?settings=1")
    project, pages = _project_state(gui_settings, project_id)
    assert project.output_profile["calendar"]["language"] == "en_US"
    assert project.output_profile["calendar"]["holiday_countries"] == ["SN", "DE"]
    assert project.output_profile["size"]["dpi"] == 150
    assert project.output_profile["style"]["background_color"] == "#000000"
    assert all(page.render_revision == 1 for page in pages)

    response = client.get(f"/projects/{project_id}?settings=1")
    assert response.status_code == 200
    assert "Project settings saved." in response.text

    response = client.get(f"/projects/{project_id}/settings")
    assert 'value="150"' in response.text
    assert 'value="#000000"' in response.text

    client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(
            **{
                "calendar.language": "en_US",
                "calendar.holiday_countries": "SN, DE",
                "size.dpi": "150",
                "style.background_color": "#000000",
            }
        ),
    )
    _, pages_after_repeat = _project_state(gui_settings, project_id)
    assert all(page.render_revision == 1 for page in pages_after_repeat)


def test_settings_save_persists_nested_font_values(client: TestClient, gui_settings: GuiSettings):
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(
            **{
                "style.font_large.size": "7.5",
                "style.font_large.color": "#123456",
                "style.font_small.size": "3.5",
                "style.font_small.color": "#654321",
                "style.font_description.size": "4.5",
                "style.font_description.color": "#00ff00",
                "style.font_anniversaries.size": "1.5",
                "style.font_anniversaries.color": "#ff00ff",
            }
        ),
        follow_redirects=False,
    )

    assert response.status_code == 303
    project, _ = _project_state(gui_settings, project_id)
    style = project.output_profile["style"]
    assert style["font_large"] == {
        "name": "DejaVuSans.ttf",
        "size": 7.5,
        "color": "#123456",
    }
    assert style["font_small"] == {
        "name": "DejaVuSans.ttf",
        "size": 3.5,
        "color": "#654321",
    }
    assert style["font_description"] == {
        "name": "DejaVuSans.ttf",
        "size": 4.5,
        "color": "#00ff00",
    }
    assert style["font_anniversaries"] == {
        "name": "DejaVuSans.ttf",
        "size": 1.5,
        "color": "#ff00ff",
    }

    page = client.get(f"/projects/{project_id}/settings").text
    assert 'name="style.font_large.size"' in page
    assert 'value="7.5"' in page
    assert 'value="#123456"' in page


def test_settings_reject_invalid_values_without_changes(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)
    before_project, before_pages = _project_state(gui_settings, project_id)

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(**{"size.dpi": "0"}),
    )

    assert response.status_code == 400
    assert "dpi must be" in response.text
    assert 'value="0"' in response.text
    after_project, after_pages = _project_state(gui_settings, project_id)
    assert after_project.output_profile == before_project.output_profile
    assert [page.render_revision for page in after_pages] == [
        page.render_revision for page in before_pages
    ]

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(**{"style.background_color": "not-a-color"}),
    )
    assert response.status_code == 400
    assert "#rrggbb" in response.text


def test_settings_are_isolated_between_projects(client: TestClient, gui_settings: GuiSettings):
    first_id = _create_project(client, name="First")
    second_id = _create_project(client, name="Second")

    client.post(
        f"/projects/{first_id}/settings",
        data=_settings_form(**{"size.dpi": "150"}),
    )

    first, first_pages = _project_state(gui_settings, first_id)
    second, second_pages = _project_state(gui_settings, second_id)
    assert first.output_profile["size"]["dpi"] == 150
    assert second.output_profile == OutputProfile.default().to_dict()
    assert all(page.render_revision == 1 for page in first_pages)
    assert all(page.render_revision == 0 for page in second_pages)


def test_project_calendar_can_shift_and_extend_with_last_layout(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)
    with _database(gui_settings).transaction() as connection:
        pages = PageRepository(connection).list(project_id)
        layout = LayoutRepository(connection).add(
            "custom",
            1,
            "Custom",
            [
                LayoutSlot(
                    id=0,
                    layout_id=0,
                    slot_key="main",
                    position=0,
                    x=0,
                    y=0,
                    width=1,
                    height=1,
                    z_index=0,
                    crop_mode="cover",
                )
            ],
        )
        PageRepository(connection).set_layout(pages[-1].id, layout.id, layout.version)

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(
            **{
                "project.name": "Renamed calendar",
                "project.start_date": "2027-02-01",
                "project.page_count": "3",
            }
        ),
        follow_redirects=False,
    )

    assert response.status_code == 303
    project, pages = _project_state(gui_settings, project_id)
    assert project.name == "Renamed calendar"
    assert project.page_count == 3
    assert [page.start_date for page in pages] == [
        "2027-02-01",
        "2027-02-08",
        "2027-02-15",
    ]
    assert pages[1].layout_id == pages[2].layout_id


def test_calendar_shrink_requires_confirmation_for_page_content(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)
    with _database(gui_settings).transaction() as connection:
        pages = PageRepository(connection).list(project_id)
        PageRepository(connection).update_description(pages[-1].id, "Keep this memory")

    data = _settings_form(**{"project.page_count": "1"})
    response = client.post(f"/projects/{project_id}/settings", data=data)
    assert response.status_code == 400
    assert "requires confirmation" in response.text
    assert len(_project_state(gui_settings, project_id)[1]) == 2

    data["project.confirm_remove"] = "1"
    response = client.post(
        f"/projects/{project_id}/settings",
        data=data,
        follow_redirects=False,
    )
    assert response.status_code == 303
    project, pages = _project_state(gui_settings, project_id)
    assert project.page_count == 1
    assert len(pages) == 1


def test_duplicate_project_route_creates_independent_copy(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/duplicate",
        data={"name": "Holiday Calendar"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    duplicate_url = response.headers["location"]
    duplicate_id = int(urlsplit(duplicate_url).path.split("/")[-1])
    assert duplicate_id != project_id

    response = client.get(duplicate_url)
    assert response.status_code == 200
    assert "Holiday Calendar" in response.text
    assert "Project duplicated. Review the copy before editing." in response.text

    source, source_pages = _project_state(gui_settings, project_id)
    duplicate, duplicate_pages = _project_state(gui_settings, duplicate_id)
    assert source.name == "Family Calendar"
    assert duplicate.name == "Holiday Calendar"
    assert duplicate.output_profile == source.output_profile
    assert [page.start_date for page in duplicate_pages] == [
        page.start_date for page in source_pages
    ]
    assert duplicate_pages[0].id != source_pages[0].id

    client.post(
        f"/projects/{duplicate_id}/settings",
        data=_settings_form(**{"size.dpi": "150"}),
    )
    source_after, source_pages_after = _project_state(gui_settings, project_id)
    assert source_after.output_profile["size"]["dpi"] == 300
    assert all(page.render_revision == 0 for page in source_pages_after)


def test_duplicate_project_route_rejects_blank_name(client: TestClient):
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/duplicate",
        data={"name": "   "},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/projects" in response.headers["location"]
    assert "name" in response.headers["location"]
