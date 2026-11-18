"""Tests for project repositories, constraints and transactional invariants."""

from __future__ import annotations

import sqlite3

import pytest

from Photo_Composition_Designer.project.errors import (
    CrossProjectAssignmentError,
    DuplicatePhotoAssignmentError,
    DuplicateSlotAssignmentError,
    SlotLayoutMismatchError,
)
from Photo_Composition_Designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    SourceRootRepository,
)
from tests.project_test_helpers import (
    add_source_root,
    make_database,
    make_layout,
    make_photo,
    make_project,
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


@pytest.fixture
def project(service):
    return make_project(service)


@pytest.fixture
def connection(database):
    return database.connect()


@pytest.fixture
def layout(connection):
    layout = make_layout(LayoutRepository(connection), slot_count=2)
    connection.commit()
    return layout


@pytest.fixture
def source_root(connection, project):
    root = add_source_root(SourceRootRepository(connection), project.id)
    connection.commit()
    return root


@pytest.fixture
def photo(connection, project, source_root):
    photo = make_photo(PhotoRepository(connection), project.id, source_root.id)
    connection.commit()
    return photo


@pytest.fixture
def page(connection, project, layout):
    repository = PageRepository(connection)
    stored = repository.list(project.id)[0]
    repository.set_layout(stored.id, layout.id, layout.version)
    connection.commit()
    return repository.get(stored.id)


def test_assign_photo_to_slot(connection, project, page, photo, layout):
    assignment = AssignmentRepository(connection).assign(
        project.id, page.id, layout.slots[0].id, photo.id
    )

    assert assignment.project_id == project.id
    assert assignment.page_id == page.id
    assert assignment.slot_id == layout.slots[0].id
    assert assignment.photo_id == photo.id
    assert assignment.crop_zoom == 1.0
    assert assignment.crop_focus_x == 0.5
    assert assignment.crop_focus_y == 0.5


def test_unassigned_pool_excludes_assigned_photo(connection, project, page, photo, layout):
    repository = PhotoRepository(connection)
    assert [item.id for item in repository.list_unassigned(project.id)] == [photo.id]

    AssignmentRepository(connection).assign(project.id, page.id, layout.slots[0].id, photo.id)

    assert repository.list_unassigned(project.id) == []


def test_remove_assignment_returns_photo_to_pool(connection, project, page, photo, layout):
    assignment_repository = AssignmentRepository(connection)
    assignment = assignment_repository.assign(project.id, page.id, layout.slots[0].id, photo.id)

    assert assignment_repository.remove(assignment.id) is True
    assert [item.id for item in PhotoRepository(connection).list_unassigned(project.id)] == [
        photo.id
    ]


def test_duplicate_photo_assignment_is_rejected(connection, project, page, photo, layout):
    repository = AssignmentRepository(connection)
    repository.assign(project.id, page.id, layout.slots[0].id, photo.id)

    with pytest.raises(DuplicatePhotoAssignmentError):
        repository.assign(project.id, page.id, layout.slots[1].id, photo.id)


def test_duplicate_slot_occupancy_is_rejected(
    connection, project, source_root, page, photo, layout
):
    repository = AssignmentRepository(connection)
    second_photo = make_photo(
        PhotoRepository(connection), project.id, source_root.id, relative_path="photo2.jpg"
    )
    repository.assign(project.id, page.id, layout.slots[0].id, photo.id)

    with pytest.raises(DuplicateSlotAssignmentError):
        repository.assign(project.id, page.id, layout.slots[0].id, second_photo.id)


def test_cross_project_assignment_is_rejected(
    database, service, connection, project, page, photo, layout
):
    other_project = make_project(service, name="Other Calendar", page_count=1)
    page_repository = PageRepository(connection)
    other_page = page_repository.list(other_project.id)[0]
    page_repository.set_layout(other_page.id, layout.id, layout.version)
    connection.commit()

    with pytest.raises(CrossProjectAssignmentError):
        AssignmentRepository(connection).assign(
            other_project.id, other_page.id, layout.slots[0].id, photo.id
        )


def test_slot_must_belong_to_page_layout(connection, project, page, photo, layout):
    other_layout = make_layout(
        LayoutRepository(connection), key="grid-other", version=1, slot_count=1
    )
    connection.commit()

    with pytest.raises(SlotLayoutMismatchError):
        AssignmentRepository(connection).assign(
            project.id, page.id, other_layout.slots[0].id, photo.id
        )


def test_upsert_refreshes_photo_without_duplicating(connection, project, source_root):
    repository = PhotoRepository(connection)
    first = make_photo(repository, project.id, source_root.id)
    second = make_photo(repository, project.id, source_root.id, file_size=456)

    assert first.id == second.id
    assert len(repository.list(project.id)) == 1
    stored = repository.get(first.id)
    assert stored is not None
    assert stored.file_size == 456


def test_unique_page_index_is_enforced(connection, project):
    with pytest.raises(sqlite3.IntegrityError):
        PageRepository(connection).create(project.id, 0, "2027-01-04", "2027-01-10")


def test_layout_roundtrip_preserves_normalized_slots(connection):
    layout = make_layout(LayoutRepository(connection), slot_count=2)

    stored = LayoutRepository(connection).get(layout.key, layout.version)

    assert stored is not None
    assert [slot.slot_key for slot in stored.slots] == ["slot_1", "slot_2"]
    assert [slot.position for slot in stored.slots] == [0, 1]
    assert all(slot.width == 1.0 for slot in stored.slots)


def test_assignment_transaction_rolls_back(database, connection, project, page, photo, layout):
    with pytest.raises(RuntimeError, match="rollback"):
        with database.transaction() as transaction_connection:
            AssignmentRepository(transaction_connection).assign(
                project.id, page.id, layout.slots[0].id, photo.id
            )
            raise RuntimeError("rollback")

    assert AssignmentRepository(connection).list_by_project(project.id) == []
