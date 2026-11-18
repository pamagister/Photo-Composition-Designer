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
from photo_composition_designer.project.repositories import (
    LayoutRepository,
    PageRepository,
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


def test_render_project_writes_pdf(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    exporter = ProjectExporter(database)
    result = exporter.render_project(project_id, tmp_path / "out", write_pdf=True)
    assert result.pdf_path is not None
    assert result.pdf_path.read_bytes().startswith(b"%PDF-")


def test_render_page_with_no_assignments_is_skipped(tmp_path, monkeypatch):
    database, project_id = _setup_project(tmp_path, monkeypatch)
    # Remove all assignments to make pages unrenderable
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
    assert len(result.rendered) == 0
    assert len(result.warnings) == 2
