"""Tests for automatic pages in distribution and project settings."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.layouts.loader import AUTO_LAYOUT_KEY, AUTO_LAYOUT_NAME
from photo_composition_designer.project.distribution import DistributionService
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.rendering import profile_from_project
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    ProjectRepository,
)
from photo_composition_designer.project.services import ProjectService


def _write_photo(path: Path, width: int = 1600, height: int = 1200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (30, 40, 50)).save(path)


def _setup(
    tmp_path: Path,
    *,
    photo_count: int = 3,
    page_count: int = 1,
    auto_target_slots: int = 6,
    width: int = 216,
    height: int = 154,
) -> tuple[WorkspaceDatabase, int, list[int], int]:
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    profile = replace(
        OutputProfile.default(),
        layout=replace(
            OutputProfile.default().layout,
            auto_target_slots=auto_target_slots,
        ),
        size=replace(OutputProfile.default().size, width=width, height=height),
    )
    project = ProjectService(database).create_project(
        name="Auto distribution",
        page_count=page_count,
        start_date=datetime(2027, 1, 4),
        output_profile=profile.to_dict(),
    )
    source = tmp_path / "source"
    for index in range(photo_count):
        _write_photo(source / f"photo_{index:02d}.jpg")
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    with database.transaction() as connection:
        layout_repo = LayoutRepository(connection)
        page_repo = PageRepository(connection)
        layout = layout_repo.add(AUTO_LAYOUT_KEY, 1, AUTO_LAYOUT_NAME, [])
        for page in page_repo.list(project.id):
            page_repo.set_layout(page.id, layout.id, layout.version)

    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
        photo_ids = [row["id"] for row in connection.execute("SELECT id FROM photos ORDER BY id")]
    return database, project.id, page.id, photo_ids


def _page_layout_and_assignments(database: WorkspaceDatabase, page_id: int):
    with database.connect() as connection:
        page = PageRepository(connection).get(page_id)
        assert page is not None and page.layout_id is not None
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        assert layout is not None
        assignments = AssignmentRepository(connection).list_by_page(page_id)
        return layout, assignments


def test_auto_page_capacity_uses_target_slot_count(tmp_path: Path) -> None:
    database, project_id, _page_id, photo_ids = _setup(tmp_path, photo_count=3, auto_target_slots=2)
    try:
        distribution = DistributionService(database)
        proposal = distribution.propose(project_id, strategy="equal")

        assert sum(len(group) for group in proposal.pages) == 2
        assert proposal.unassigned == photo_ids[2:]
    finally:
        database.close()


def test_apply_auto_page_generates_a_valid_tiling(tmp_path: Path) -> None:
    database, project_id, page_id, _photo_ids = _setup(tmp_path, photo_count=3, auto_target_slots=2)
    try:
        distribution = DistributionService(database)
        proposal = distribution.propose(project_id, strategy="equal")
        distribution.apply(project_id, proposal)

        layout, assignments = _page_layout_and_assignments(database, page_id)
        assert layout.key == AUTO_LAYOUT_KEY
        assert len(layout.slots) == 2
        assert len(assignments) == 2
        assert {assignment.slot_id for assignment in assignments} == {
            slot.id for slot in layout.slots
        }

        coverage = sum(slot.width * slot.height for slot in layout.slots)
        assert coverage == 1.0
        assert all(0.0 < slot.width <= 1.0 for slot in layout.slots)
        assert all(0.0 < slot.height <= 1.0 for slot in layout.slots)
    finally:
        database.close()


def test_apply_auto_page_keeps_one_slot_per_assigned_photo(tmp_path: Path) -> None:
    database, project_id, page_id, _photo_ids = _setup(tmp_path, photo_count=4, auto_target_slots=6)
    try:
        distribution = DistributionService(database)
        proposal = distribution.propose(project_id, strategy="equal")
        distribution.apply(project_id, proposal)

        layout, assignments = _page_layout_and_assignments(database, page_id)
        assert len(assignments) == 4
        assert len(layout.slots) == 4
        assert {assignment.slot_id for assignment in assignments} == {
            slot.id for slot in layout.slots
        }
    finally:
        database.close()


def test_regenerate_auto_layouts_follows_new_canvas_aspect(tmp_path: Path) -> None:
    database, project_id, page_id, photo_ids = _setup(
        tmp_path, photo_count=2, width=216, height=154
    )
    try:
        editing = PageEditingService(database)
        editing.auto_add(project_id, page_id, photo_ids[0])
        editing.auto_add(project_id, page_id, photo_ids[1])
        first_layout, _ = _page_layout_and_assignments(database, page_id)
        assert all(slot.y == 0.0 for slot in first_layout.slots)

        with database.connect() as connection:
            project = ProjectRepository(connection).get(project_id)
            assert project is not None
            current = profile_from_project(project)
            portrait = replace(current, size=replace(current.size, width=154, height=216))
            ProjectService(database).update_output_profile(project_id, portrait)

        regenerated = editing.regenerate_auto_layouts(project_id)
        assert regenerated == 1

        layout, _ = _page_layout_and_assignments(database, page_id)
        assert layout.id != first_layout.id
        assert all(slot.width == 1.0 for slot in layout.slots)
        assert layout.slots[0].y == 0.0
        assert layout.slots[1].y > 0.0
    finally:
        database.close()
