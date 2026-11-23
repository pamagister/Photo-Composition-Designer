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
        "geo.map_mode": profile.geo.map_mode,
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
        "layout.text_margin": str(profile.layout.text_margin),
        "layout.description_alignment": profile.layout.description_alignment,
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
    assert 'name="geo.map_mode"' in response.text
    assert 'name="layout.text_margin"' in response.text
    assert 'name="layout.description_alignment"' in response.text
    assert 'name="layout.auto_target_slots"' not in response.text
    assert 'name="layout.generate_pdf"' not in response.text
    assert "Duplicate project" not in response.text


def test_settings_page_has_top_and_bottom_save_and_cancel(client: TestClient):
    project_id = _create_project(client)

    response = client.get(f"/projects/{project_id}/settings")

    assert response.status_code == 200
    # Top and bottom each expose a Save and a Cancel control side by side.
    assert response.text.count(">Save</button>") == 2
    assert response.text.count(">Cancel</a>") == 2
    # The top Save is bound to the settings form even though it sits in the header.
    assert 'id="project-settings-form"' in response.text
    assert 'form="project-settings-form"' in response.text
    # Only the agreed labels are used (no legacy "Save settings" / "Back to project").
    assert "Save settings" not in response.text
    assert "Back to project" not in response.text


def test_settings_save_persists_image_score_factor(client: TestClient, gui_settings: GuiSettings):
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(**{"layout.image_score_factor": "3.5"}),
        follow_redirects=False,
    )

    assert response.status_code == 303
    project, _pages = _project_state(gui_settings, project_id)
    profile = OutputProfile.from_dict(project.output_profile)
    assert profile.layout.image_score_factor == pytest.approx(3.5)


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


def test_projects_page_renders_project_tiles_with_actions(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    projects = client.get("/projects")

    assert projects.status_code == 200
    assert 'class="project-card"' in projects.text
    assert f'href="/projects/{project_id}"' in projects.text
    assert "project-card-placeholder" in projects.text
    assert "Updated " in projects.text
    assert "2 pages" in projects.text
    assert "2027" in projects.text
    assert f'action="/projects/{project_id}/duplicate"' in projects.text
    assert ">Duplicate</button>" in projects.text
    assert f'href="/projects/{project_id}/archive"' in projects.text
    assert "Export .pcd" in projects.text
    assert f'action="/projects/{project_id}/delete"' in projects.text
    assert 'class="danger icon-button"' in projects.text
    assert 'aria-label="Delete Family Calendar"' in projects.text
    assert "return confirm(" in projects.text
    assert 'name="name"' not in projects.text
    assert 'action="/projects/import-pcd"' in projects.text
    assert "Import project (.pcd)" in projects.text


def test_projects_page_uses_cached_first_page_preview_as_title_image(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)
    _, pages = _project_state(gui_settings, project_id)

    preview = client.get(f"/projects/{project_id}/pages/{pages[0].id}/preview?max_width=200")
    assert preview.status_code == 200

    projects = client.get("/projects")

    assert projects.status_code == 200
    assert f"/projects/{project_id}/preview-assets/" in projects.text
    assert "project-card-placeholder" not in projects.text


def test_delete_project_route_removes_project_and_returns_to_list(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    response = client.post(f"/projects/{project_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/projects?deleted=1"
    assert client.get(f"/projects/{project_id}").status_code == 404

    listing = client.get("/projects?deleted=1")
    assert listing.status_code == 200
    assert "Project deleted." in listing.text
    assert f"/projects/{project_id}" not in listing.text


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


def test_settings_save_persists_map_and_layout_fields(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(
            **{
                "geo.map_mode": "always",
                "layout.text_margin": "2.5",
                "layout.description_alignment": "center",
            }
        ),
        follow_redirects=False,
    )

    assert response.status_code == 303
    project, _ = _project_state(gui_settings, project_id)
    profile = OutputProfile.from_dict(project.output_profile)
    assert profile.geo.map_mode == "always"
    assert profile.layout.text_margin == 2.5
    assert profile.layout.description_alignment == "center"


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


def test_page_count_change_does_not_regenerate_auto_layouts(
    client: TestClient, gui_settings: GuiSettings, monkeypatch: pytest.MonkeyPatch
):
    from photo_composition_designer.project import editing as editing_module

    project_id = _create_project(client)
    _, pages_before = _project_state(gui_settings, project_id)
    revisions_before = {page.id: page.render_revision for page in pages_before}

    calls: list[int] = []
    original = editing_module.PageEditingService.regenerate_auto_layouts

    def spy(self, project_id, **kwargs):
        calls.append(project_id)
        return original(self, project_id, **kwargs)

    monkeypatch.setattr(editing_module.PageEditingService, "regenerate_auto_layouts", spy)

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(**{"project.page_count": "3"}),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert calls == []
    _, pages_after = _project_state(gui_settings, project_id)
    after_by_id = {page.id: page for page in pages_after}
    # Existing pages keep their render revision (and cached preview).
    for page in pages_before:
        assert after_by_id[page.id].render_revision == revisions_before[page.id]
    # Exactly one new page was added.
    new_pages = [page for page in pages_after if page.id not in revisions_before]
    assert len(new_pages) == 1


def test_profile_change_regenerates_auto_layouts(
    client: TestClient, gui_settings: GuiSettings, monkeypatch: pytest.MonkeyPatch
):
    from photo_composition_designer.project import editing as editing_module

    project_id = _create_project(client)

    calls: list[int] = []
    original = editing_module.PageEditingService.regenerate_auto_layouts

    def spy(self, project_id, **kwargs):
        calls.append(project_id)
        return original(self, project_id, **kwargs)

    monkeypatch.setattr(editing_module.PageEditingService, "regenerate_auto_layouts", spy)

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(**{"size.dpi": "150"}),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert calls == [project_id]


def test_page_count_increase_renders_new_page_preview(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)
    _, pages_before = _project_state(gui_settings, project_id)
    before_ids = {page.id for page in pages_before}

    response = client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(**{"project.page_count": "3"}),
        follow_redirects=False,
    )
    assert response.status_code == 303

    _, pages_after = _project_state(gui_settings, project_id)
    new_pages = [page for page in pages_after if page.id not in before_ids]
    assert len(new_pages) == 1
    new_page = new_pages[0]

    # Both thumbnail and large preview were enqueued (and rendered inline by
    # the synchronous worker), so the new page serves cached JPEGs.
    for max_width in (200, 800):
        preview = client.get(
            f"/projects/{project_id}/pages/{new_page.id}/preview",
            params={"max_width": max_width},
        )
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/jpeg"


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


def test_duplicate_project_route_generates_incrementing_copy_names(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)

    first = client.post(f"/projects/{project_id}/duplicate", follow_redirects=False)
    assert first.status_code == 303
    first_id = int(urlsplit(first.headers["location"]).path.split("/")[-1])

    second = client.post(f"/projects/{project_id}/duplicate", follow_redirects=False)
    assert second.status_code == 303
    second_id = int(urlsplit(second.headers["location"]).path.split("/")[-1])

    first_project, _ = _project_state(gui_settings, first_id)
    second_project, _ = _project_state(gui_settings, second_id)
    assert first_project.name == "Family Calendar copy"
    assert second_project.name == "Family Calendar copy-1"


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


def test_settings_page_shows_calendar_language_and_holiday_choices(
    client: TestClient,
):
    project_id = _create_project(client)

    response = client.get(f"/projects/{project_id}/settings")

    assert response.status_code == 200
    assert 'name="calendar.language"' in response.text
    assert '<option value="de_DE"' in response.text
    assert '<option value="de_AT"' in response.text
    assert '<option value="en_US"' in response.text
    assert 'data-holiday-country="DE"' in response.text
    assert 'value="SN"' in response.text
    assert 'data-holiday-country="US"' in response.text
    assert 'value="CA"' in response.text
    assert 'data-holiday-country="IT"' in response.text
    assert "Italy uses nationwide holidays." in response.text


def test_settings_save_persists_multiple_holiday_subdivisions(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)
    form = _settings_form(**{"calendar.language": "de_AT"})
    data = {key: value for key, value in form.items() if key != "calendar.holiday_countries"}
    data["calendar.holiday_countries"] = ["1", "9"]

    response = client.post(
        f"/projects/{project_id}/settings",
        data=data,
        follow_redirects=False,
    )

    assert response.status_code == 303
    project, _ = _project_state(gui_settings, project_id)
    profile = OutputProfile.from_dict(project.output_profile)
    assert profile.calendar.language == "de_AT"
    assert profile.calendar.holiday_countries == ("1", "9")


def test_settings_save_without_holiday_subdivisions_uses_nationwide(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)
    form = _settings_form()
    data = {key: value for key, value in form.items() if key != "calendar.holiday_countries"}

    response = client.post(
        f"/projects/{project_id}/settings",
        data=data,
        follow_redirects=False,
    )

    assert response.status_code == 303
    project, _ = _project_state(gui_settings, project_id)
    profile = OutputProfile.from_dict(project.output_profile)
    assert profile.calendar.holiday_countries == ()


def test_settings_page_keeps_legacy_holiday_values_visible(
    client: TestClient, gui_settings: GuiSettings
):
    project_id = _create_project(client)
    client.post(
        f"/projects/{project_id}/settings",
        data=_settings_form(
            **{
                "calendar.language": "en_US",
                "calendar.holiday_countries": "SN, BY",
            }
        ),
        follow_redirects=False,
    )

    response = client.get(f"/projects/{project_id}/settings")

    assert response.status_code == 200
    assert "SN (current)" in response.text
    assert "BY (current)" in response.text
