"""Tests for project lifecycle services and settings snapshots."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from photo_composition_designer.core.errors import ProjectNotFoundError
from photo_composition_designer.core.output_profile import OutputProfile, OutputProfileError
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    SourceRootRepository,
)
from tests.project_test_helpers import (
    make_database,
    make_layout,
    make_photo,
    make_service,
)


@pytest.fixture
def database(tmp_path):
    database = make_database(tmp_path)
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def service(database):
    return make_service(database)


def test_create_project_creates_explicit_weekly_pages(service, database):
    project = service.create_project(
        name="Calendar",
        page_count=3,
        start_date=datetime(2027, 1, 4),
    )

    pages = PageRepository(database.connect()).list(project.id)

    assert [page.page_index for page in pages] == [0, 1, 2]
    assert [page.start_date for page in pages] == [
        "2027-01-04",
        "2027-01-11",
        "2027-01-18",
    ]
    assert [page.end_date for page in pages] == [
        "2027-01-10",
        "2027-01-17",
        "2027-01-24",
    ]
    assert project.calendar_year == 2027
    assert project.page_count == 3


def test_close_and_reopen_preserves_project_state(service):
    project = service.create_project(
        name="Family Calendar",
        page_count=2,
        start_date=datetime(2027, 1, 4),
        settings={"calendar": {"language": "en_US"}},
        output_profile={"size": {"dpi": 300}},
    )
    service.save_project(
        project.id,
        settings={"calendar": {"language": "de_DE"}, "style": {"theme": "dark"}},
    )

    service.close_project(project.id)
    reopened = service.open_project(project.id)

    assert reopened.project.name == project.name
    assert reopened.project.settings == {
        "calendar": {"language": "de_DE"},
        "style": {"theme": "dark"},
    }
    assert reopened.project.output_profile["size"]["dpi"] == 300
    assert reopened.project.output_profile["size"]["width"] == 216
    assert reopened.project.output_profile["calendar"]["language"] == "de_DE"
    assert len(reopened.pages) == 2
    assert [page.page_index for page in reopened.pages] == [0, 1]


def test_save_project_updates_name_and_output_profile(service):
    project = service.create_project(
        name="Calendar",
        page_count=1,
        start_date=datetime(2027, 1, 4),
    )

    updated = service.save_project(
        project.id,
        name="Renamed Calendar",
        output_profile={"size": {"dpi": 150}},
    )

    assert updated.name == "Renamed Calendar"
    assert updated.output_profile == {"size": {"dpi": 150}}
    assert service.get_project(project.id).name == "Renamed Calendar"


def test_create_project_rejects_invalid_input(service):
    with pytest.raises(ValueError, match="name"):
        service.create_project(
            name=" ",
            page_count=1,
            start_date=datetime(2027, 1, 4),
        )

    with pytest.raises(ValueError, match="page_count"):
        service.create_project(
            name="Calendar",
            page_count=0,
            start_date=datetime(2027, 1, 4),
        )


def test_list_projects_returns_created_projects(service):
    first = service.create_project(
        name="First",
        page_count=1,
        start_date=datetime(2027, 1, 4),
    )
    second = service.create_project(
        name="Second",
        page_count=1,
        start_date=datetime(2028, 1, 3),
    )

    assert [project.id for project in service.list_projects()] == [first.id, second.id]


def test_open_missing_project_raises(service):
    with pytest.raises(ProjectNotFoundError):
        service.open_project(999)


def _seed_project_with_assignment(service, database):
    """Create a project with a source root, photo, layout and one assignment."""
    project = service.create_project(
        name="Family Calendar",
        page_count=2,
        start_date=datetime(2027, 1, 4),
        settings={"calendar": {"language": "de_DE"}},
        output_profile={"size": {"dpi": 150}},
    )
    with database.transaction() as connection:
        root = SourceRootRepository(connection).add(
            project.id,
            "/photos",
            active=True,
            source_identity="/photos",
            last_scan_at="2026-11-18T00:00:00+00:00",
        )
        photo = make_photo(PhotoRepository(connection), project.id, root.id)
        layout = make_layout(LayoutRepository(connection), key="grid-2", slot_count=2)
        page_repository = PageRepository(connection)
        first_page = page_repository.list(project.id)[0]
        page_repository.set_layout(first_page.id, layout.id, layout.version)
        page_repository.update_description(first_page.id, "First week")
        AssignmentRepository(connection).assign(
            project.id,
            first_page.id,
            layout.slots[0].id,
            photo.id,
            crop_zoom=1.4,
            crop_focus_x=0.25,
            crop_focus_y=0.75,
        )
    return project, layout


def test_update_output_profile_snapshots_and_invalidates_pages(service, database):
    project = _seed_project_with_assignment(service, database)[0]
    before_revisions = [
        page.render_revision for page in PageRepository(database.connect()).list(project.id)
    ]

    updated = service.update_output_profile(
        project.id,
        {"size": {"dpi": 150}, "calendar": {"language": "en_US"}},
    )

    pages = PageRepository(database.connect()).list(project.id)
    assert updated.output_profile["size"]["dpi"] == 150
    assert updated.output_profile["size"]["width"] == 216
    assert updated.output_profile["calendar"]["language"] == "en_US"
    assert [page.render_revision for page in pages] == [
        revision + 1 for revision in before_revisions
    ]

    service.update_output_profile(project.id, updated.output_profile)
    assert [
        page.render_revision for page in PageRepository(database.connect()).list(project.id)
    ] == [revision + 1 for revision in before_revisions]


def test_update_output_profile_rejects_invalid_values(service, database):
    project = _seed_project_with_assignment(service, database)[0]
    before = service.get_project(project.id)
    revisions = [
        page.render_revision for page in PageRepository(database.connect()).list(project.id)
    ]

    with pytest.raises(OutputProfileError, match="dpi"):
        service.update_output_profile(project.id, {"size": {"dpi": 0}})
    with pytest.raises(OutputProfileError, match="background_color"):
        service.update_output_profile(project.id, {"style": {"background_color": "red"}})

    assert service.get_project(project.id).output_profile == before.output_profile
    assert [
        page.render_revision for page in PageRepository(database.connect()).list(project.id)
    ] == revisions


def test_update_output_profile_is_project_scoped(service, database):
    first = service.create_project(name="First", page_count=1, start_date=datetime(2027, 1, 4))
    second = service.create_project(name="Second", page_count=1, start_date=datetime(2027, 1, 4))

    service.update_output_profile(first.id, {"size": {"dpi": 150}})

    second_after = service.get_project(second.id)
    assert second_after.output_profile == OutputProfile.default().to_dict()
    assert PageRepository(database.connect()).list(second.id)[0].render_revision == 0


def test_duplicate_project_copies_state_and_stays_independent(service, database):
    project, layout = _seed_project_with_assignment(service, database)

    duplicate = service.duplicate_project(project.id)

    assert duplicate.id != project.id
    assert duplicate.name == "Family Calendar copy"
    assert duplicate.output_profile == service.get_project(project.id).output_profile
    assert duplicate.settings == project.settings

    with database.connect() as connection:
        source_pages = PageRepository(connection).list(project.id)
        copied_pages = PageRepository(connection).list(duplicate.id)
        source_roots = SourceRootRepository(connection).list(project.id)
        copied_roots = SourceRootRepository(connection).list(duplicate.id)
        source_photos = PhotoRepository(connection).list(project.id)
        copied_photos = PhotoRepository(connection).list(duplicate.id)
        source_assignments = AssignmentRepository(connection).list_by_project(project.id)
        copied_assignments = AssignmentRepository(connection).list_by_project(duplicate.id)

    assert [page.start_date for page in copied_pages] == [page.start_date for page in source_pages]
    assert [page.description for page in copied_pages] == [
        page.description for page in source_pages
    ]
    assert copied_pages[0].description == "First week"
    assert copied_pages[0].layout_id == layout.id
    assert copied_pages[0].layout_version == layout.version
    assert copied_pages[0].id != source_pages[0].id

    assert [(root.path, root.active) for root in copied_roots] == [
        (root.path, root.active) for root in source_roots
    ]
    assert copied_roots[0].last_scan_at == source_roots[0].last_scan_at
    assert copied_roots[0].id != source_roots[0].id

    assert [photo.relative_path for photo in copied_photos] == [
        photo.relative_path for photo in source_photos
    ]
    assert copied_photos[0].source_root_id == copied_roots[0].id
    assert copied_photos[0].id != source_photos[0].id

    assert len(copied_assignments) == len(source_assignments) == 1
    copied_assignment = copied_assignments[0]
    assert copied_assignment.project_id == duplicate.id
    assert copied_assignment.page_id == copied_pages[0].id
    assert copied_assignment.photo_id == copied_photos[0].id
    assert copied_assignment.slot_id == source_assignments[0].slot_id
    assert (copied_assignment.crop_zoom, copied_assignment.crop_focus_x) == (1.4, 0.25)
    assert copied_assignment.crop_focus_y == 0.75

    service.update_output_profile(duplicate.id, {"size": {"dpi": 200}})
    service.rename_project(duplicate.id, "Duplicate")
    with database.connect() as connection:
        AssignmentRepository(connection).remove(copied_assignment.id)

    source_after = service.get_project(project.id)
    assert source_after.name == "Family Calendar"
    assert source_after.output_profile["size"]["dpi"] == 150
    with database.connect() as connection:
        assert len(AssignmentRepository(connection).list_by_project(project.id)) == 1
        assert len(AssignmentRepository(connection).list_by_project(duplicate.id)) == 0


def test_duplicate_project_requires_existing_project_and_name(service, database):
    project = service.create_project(
        name="Family Calendar", page_count=1, start_date=datetime(2027, 1, 4)
    )

    with pytest.raises(ProjectNotFoundError):
        service.duplicate_project(999)
    with pytest.raises(ValueError, match="name"):
        service.duplicate_project(project.id, name="   ")
    assert len(service.list_projects()) == 1


def test_duplicate_project_generates_incrementing_copy_names(service):
    project = service.create_project(
        name="Family Calendar", page_count=1, start_date=datetime(2027, 1, 4)
    )

    first = service.duplicate_project(project.id)
    second = service.duplicate_project(project.id)
    third = service.duplicate_project(project.id)

    assert [first.name, second.name, third.name] == [
        "Family Calendar copy",
        "Family Calendar copy-1",
        "Family Calendar copy-2",
    ]


def test_delete_project_removes_project_owned_rows(service, database):
    project = service.create_project(
        name="Delete me", page_count=1, start_date=datetime(2027, 1, 4)
    )

    service.delete_project(project.id)

    assert service.list_projects() == []
    with pytest.raises(ProjectNotFoundError):
        service.get_project(project.id)
    with database.connect() as connection:
        assert PageRepository(connection).list(project.id) == []


def test_use_title_page_toggle_updates_first_page_overrides(service, database):
    project = service.create_project(
        name="Title page",
        page_count=2,
        start_date=datetime(2027, 1, 4),
    )

    with database.connect() as connection:
        first_page = PageRepository(connection).list(project.id)[0]
        assert first_page.hide_local_map is True
        assert first_page.hide_calendar_strip is True
        assert first_page.hide_description is True

    profile = OutputProfile.from_dict(project.output_profile)
    without_title = replace(
        profile,
        calendar=replace(profile.calendar, use_title_page=False),
    )
    service.update_output_profile(project.id, without_title)

    with database.connect() as connection:
        first_page = PageRepository(connection).get(first_page.id)
    assert first_page is not None
    assert first_page.hide_local_map is False
    assert first_page.hide_calendar_strip is False
    assert first_page.hide_description is False
