from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.project_archive import (
    export_project_archive,
    import_project_archive,
)
from photo_composition_designer.project.models import LayoutSlot, PhotoAsset
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
    SourceRootRepository,
)
from photo_composition_designer.project.services import ProjectService


def _create_project(database: WorkspaceDatabase) -> int:
    project = ProjectService(database).create_project(
        name="Archive test",
        page_count=1,
        start_date=date(2027, 1, 4),
    )
    with database.transaction() as connection:
        root = SourceRootRepository(connection).add(project.id, "/external/photos", active=True)
        PhotoRepository(connection).upsert_many(
            [
                PhotoAsset(
                    id=0,
                    project_id=project.id,
                    source_root_id=root.id,
                    relative_path="family/photo.jpg",
                    filename="photo.jpg",
                    file_size=4,
                    mtime=1.0,
                    digest="test",
                    width=20,
                    height=10,
                    captured_at=None,
                    gps_lat=50.0,
                    gps_lon=8.0,
                    available=True,
                    created_at=project.created_at,
                )
            ]
        )
        photo = PhotoRepository(connection).list(project.id)[0]
        layout = LayoutRepository(connection).add(
            "archive_test",
            1,
            "Archive test layout",
            [
                LayoutSlot(
                    id=0,
                    layout_id=0,
                    slot_key="slot-1",
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
        page = PageRepository(connection).list(project.id)[0]
        PageRepository(connection).set_layout(page.id, layout.id, layout.version)
        AssignmentRepository(connection).assign(project.id, page.id, layout.slots[0].id, photo.id)
    return project.id


def test_pcd_roundtrip_preserves_project_references_without_photo_files(tmp_path):
    source_database = WorkspaceDatabase(tmp_path / "source.sqlite3")
    project_id = _create_project(source_database)
    archive_data = export_project_archive(source_database, project_id)

    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        assert archive.namelist() == ["project.json"]
        assert b"source photo content" not in archive.read("project.json")

    destination_database = WorkspaceDatabase(tmp_path / "destination.sqlite3")
    imported = import_project_archive(destination_database, archive_data)
    assert imported.name == "Archive test"

    with destination_database.connect() as connection:
        project = ProjectRepository(connection).get(imported.id)
        pages = PageRepository(connection).list(imported.id)
        roots = SourceRootRepository(connection).list(imported.id)
        photos = PhotoRepository(connection).list(imported.id)
        assignments = AssignmentRepository(connection).list_by_project(imported.id)

    assert project is not None
    assert len(pages) == len(roots) == len(photos) == len(assignments) == 1
    assert roots[0].path == "/external/photos"
    assert photos[0].relative_path == "family/photo.jpg"
    assert assignments[0].crop_zoom == 1.0
    source_database.close()
    destination_database.close()


def test_pcd_import_rejects_archives_with_extra_members(tmp_path):
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w") as archive:
        archive.writestr("project.json", "{}")
        archive.writestr("../outside.txt", "unsafe")

    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    with pytest.raises(ValueError, match="only project.json"):
        import_project_archive(database, archive_data.getvalue())
    with database.connect() as connection:
        assert ProjectRepository(connection).list() == []
    database.close()
