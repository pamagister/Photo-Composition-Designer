"""Tests for project lifecycle services and settings snapshots."""

from __future__ import annotations

from datetime import datetime

import pytest

from Photo_Composition_Designer.project.errors import ProjectNotFoundError
from Photo_Composition_Designer.project.repositories import PageRepository
from tests.project_test_helpers import make_database, make_service


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
    assert reopened.project.output_profile == {"size": {"dpi": 300}}
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
