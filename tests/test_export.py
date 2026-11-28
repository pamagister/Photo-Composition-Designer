"""Tests for ordered page rendering and PDF export from project data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.export import ProjectExporter
from photo_composition_designer.project.distribution import DistributionService
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import LayoutSlot
from photo_composition_designer.project.rendering import ProjectRenderingService
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
)
from photo_composition_designer.project.services import ProjectService


def _write_photo(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color).save(path)


def _setup_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PCD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PCD_CACHE_DIR", str(tmp_path / "cache"))

    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    service = ProjectService(database)
    project = service.create_project(
        name="Export",
        page_count=2,
        start_date=datetime(2027, 1, 4),
        settings={},
        output_profile={},
        import_metadata={"source": "test"},
    )

    source = tmp_path / "source"
    for i in range(4):
        _write_photo(source / f"p{i}.jpg", (i * 50, 0, 0))
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    with database.transaction() as connection:
        layout_repo = LayoutRepository(connection)
        page_repo = PageRepository(connection)
        for page in page_repo.list(project.id):
            slots = [
                LayoutSlot(
                    id=0,
                    layout_id=0,
                    slot_key=f"slot_{i}",
                    position=i,
                    x=i * 0.5,
                    y=0.0,
                    width=0.5,
                    height=1.0,
                    z_index=0,
                    crop_mode="cover",
                )
                for i in range(2)
            ]
            layout = layout_repo.add(f"layout_{page.page_index}", 1, "Test", slots)
            page_repo.set_layout(page.id, layout.id, 1)

    distribution = DistributionService(database)
    proposal = distribution.propose(project.id, strategy="equal")
    distribution.apply(project.id, proposal)

    return database, project.id


def test_render_project_orders_pages(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    exporter = ProjectExporter(database)
    result = exporter.render_project(project_id, tmp_path / "out", write_pdf=False)
    assert len(result.rendered) == 2
    assert result.rendered[0].name == "page_000.png"
    assert result.rendered[1].name == "page_001.png"


def test_render_input_and_warnings_use_constant_query_count(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    connection = database.connect()
    page = PageRepository(connection).list(project_id)[0]
    assignment = AssignmentRepository(connection).list_by_page(page.id)[0]
    PhotoRepository(connection).set_availability(assignment.photo_id, False)
    rendering = ProjectRenderingService(database)
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    try:
        render_input, warnings = rendering.build_input_with_warnings(connection, page)
    finally:
        connection.set_trace_callback(None)

    select_count = sum(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert select_count == 6
    assert len(render_input.assigned_photos) == 1
    assert len(warnings) == 1
    assert warnings[0].endswith(" is unavailable")
    assert warnings == rendering.assignment_warnings(connection, page)


def test_render_project_writes_pdf(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    exporter = ProjectExporter(database)
    result = exporter.render_project(project_id, tmp_path / "out", write_pdf=True)
    assert result.pdf_path is not None
    assert result.pdf_path.read_bytes().startswith(b"%PDF-")


def test_render_page_without_assignments_still_renders_calendar(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    # Remove all assignments so the page has no photos.
    editing = PageEditingService(database)
    with database.connect() as connection:
        from photo_composition_designer.project.repositories import AssignmentRepository

        assignments = AssignmentRepository(connection).list(project_id)
        page_ids = {a.page_id for a in assignments}
        slot_ids = {a.slot_id for a in assignments}
    for page_id in page_ids:
        for slot_id in slot_ids:
            editing.remove(project_id, page_id, slot_id)

    exporter = ProjectExporter(database)
    result = exporter.render_project(project_id, tmp_path / "out", write_pdf=False)
    assert len(result.rendered) == 2
    assert len(result.warnings) == 0


def test_render_project_writes_jpg_pages(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    exporter = ProjectExporter(database)

    result = exporter.render_project(
        project_id,
        tmp_path / "out",
        write_pdf=False,
        write_pages=True,
        image_format="JPEG",
        jpeg_quality=80,
        dpi=150,
    )

    assert [path.name for path in result.rendered] == ["page_000.jpg", "page_001.jpg"]
    assert result.rendered_pages == 2
    with Image.open(result.rendered[0]) as page:
        assert page.format == "JPEG"
        assert tuple(round(value) for value in page.info.get("dpi", (0, 0))) == (150, 150)


def test_render_project_pdf_only_writes_no_page_files(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    exporter = ProjectExporter(database)

    result = exporter.render_project(
        project_id,
        tmp_path / "out",
        write_pdf=True,
        write_pages=False,
        image_format="JPEG",
        dpi=100,
    )

    assert result.rendered == []
    assert result.rendered_pages == 2
    assert result.pdf_path is not None
    assert list((tmp_path / "out").glob("page_*")) == []


def test_render_project_reports_progress(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    updates: list[tuple[int, int]] = []

    ProjectExporter(database).render_project(
        project_id,
        tmp_path / "progress",
        write_pdf=False,
        progress=lambda completed, total: updates.append((completed, total)),
    )

    assert updates[0] == (0, 2)
    assert updates[-1] == (2, 2)
    assert [completed for completed, _ in updates] == [0, 1, 2]
