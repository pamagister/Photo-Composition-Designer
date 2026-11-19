"""Tests for distribution proposals and page editing services."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from photo_composition_designer.core.errors import (
    DuplicateSlotAssignmentError,
)
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.distribution import DistributionService
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import DistributionProposal, LayoutSlot
from photo_composition_designer.project.repositories import (
    LayoutRepository,
    PageRepository,
    PhotoRepository,
)
from photo_composition_designer.project.services import ProjectService


def _write_photo(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 10), color).save(path)


def _setup(
    tmp_path: Path,
    *,
    page_count: int = 2,
    photo_count: int = 4,
    slots_per_page: int = 2,
    start_date: datetime | None = None,
) -> tuple[WorkspaceDatabase, DistributionService, PageEditingService, object]:
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    service = ProjectService(database)
    project = service.create_project(
        name="Dist",
        page_count=page_count,
        start_date=start_date or datetime(2027, 1, 4),
        settings={},
        output_profile={},
        import_metadata={"source": "test"},
    )

    source = tmp_path / "source"
    for index in range(photo_count):
        _write_photo(source / f"photo_{index:02d}.jpg", (index * 30, 0, 0))
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    with database.transaction() as connection:
        layout_repo = LayoutRepository(connection)
        page_repo = PageRepository(connection)
        pages = page_repo.list(project.id)
        for page in pages:
            slots = [
                LayoutSlot(
                    id=0,
                    layout_id=0,
                    slot_key=f"slot_{i}",
                    position=i,
                    x=i * (1.0 / slots_per_page),
                    y=0.0,
                    width=1.0 / slots_per_page,
                    height=1.0,
                    z_index=0,
                    crop_mode="cover",
                )
                for i in range(slots_per_page)
            ]
            layout = layout_repo.add(f"layout_{page.page_index}", 1, "Test", slots)
            page_repo.set_layout(page.id, layout.id, 1)

    return (
        database,
        DistributionService(database),
        PageEditingService(database),
        project,
    )


def test_equal_proposal_splits_photos_across_pages(tmp_path: Path) -> None:
    database, distribution, _editing, project = _setup(
        tmp_path, page_count=2, photo_count=4, slots_per_page=2
    )
    proposal = distribution.propose(project.id, strategy="equal")
    assert len(proposal.pages) == 2
    assert sum(len(group) for group in proposal.pages) == 4


def test_equal_proposal_overflow_stays_unassigned(tmp_path: Path) -> None:
    database, distribution, _editing, project = _setup(
        tmp_path, page_count=1, photo_count=3, slots_per_page=2
    )
    proposal = distribution.propose(project.id, strategy="equal")
    assigned = sum(len(group) for group in proposal.pages)
    assert assigned == 2
    assert len(proposal.unassigned) == 1


def test_random_proposal_is_reproducible(tmp_path: Path) -> None:
    database, distribution, _editing, project = _setup(
        tmp_path, page_count=2, photo_count=4, slots_per_page=2
    )
    first = distribution.propose(project.id, strategy="random", seed=42)
    second = distribution.propose(project.id, strategy="random", seed=42)
    assert first.pages == second.pages
    assert first.seed == 42


def test_proposal_does_not_mutate_assignments(tmp_path: Path) -> None:
    database, distribution, _editing, project = _setup(
        tmp_path, page_count=2, photo_count=4, slots_per_page=2
    )
    distribution.propose(project.id, strategy="equal")
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
    assert count == 0


def test_apply_proposal_persists_assignments(tmp_path: Path) -> None:
    database, distribution, _editing, project = _setup(
        tmp_path, page_count=2, photo_count=4, slots_per_page=2
    )
    proposal = distribution.propose(project.id, strategy="equal")
    distribution.apply(project.id, proposal)
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
        revisions = [page.render_revision for page in PageRepository(connection).list(project.id)]
    assert count == 4
    assert revisions == [2, 2]


def test_apply_matches_photo_orientation_to_slot_orientation(tmp_path: Path) -> None:
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    project = ProjectService(database).create_project(
        name="Orient", page_count=1, start_date=datetime(2027, 1, 4)
    )
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (20, 40), (255, 0, 0)).save(source / "portrait.jpg")
    Image.new("RGB", (40, 20), (0, 255, 0)).save(source / "landscape.jpg")
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    with database.transaction() as connection:
        page = PageRepository(connection).list(project.id)[0]
        layout = LayoutRepository(connection).add(
            "orient",
            1,
            "Orient",
            [
                LayoutSlot(0, 0, "portrait", 0, 0.0, 0.0, 0.15, 1.0, 0, "cover"),
                LayoutSlot(0, 0, "landscape", 1, 0.85, 0.0, 0.15, 1.0, 0, "cover"),
            ],
        )
        PageRepository(connection).set_layout(page.id, layout.id, 1)
        photos = {
            photo.filename: photo.id for photo in PhotoRepository(connection).list(project.id)
        }

    # Propose landscape first to prove the order is corrected on apply.
    proposal = DistributionProposal(
        strategy="equal",
        pages=[[photos["landscape.jpg"], photos["portrait.jpg"]]],
    )
    DistributionService(database).apply(project.id, proposal)

    with database.connect() as connection:
        assignments = {
            row["slot_id"]: row["photo_id"]
            for row in connection.execute("SELECT slot_id, photo_id FROM assignments").fetchall()
        }
    assert assignments[layout.slots[0].id] == photos["portrait.jpg"]
    assert assignments[layout.slots[1].id] == photos["landscape.jpg"]


def test_assign_to_empty_slot_and_unused_pool(tmp_path: Path) -> None:
    database, _distribution, editing, project = _setup(
        tmp_path, page_count=1, photo_count=2, slots_per_page=2
    )
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        photo = connection.execute("SELECT id FROM photos ORDER BY id LIMIT 1").fetchone()
        slot = layout.slots[0]

    editing.assign_to_empty_slot(project.id, page.id, slot.id, photo["id"])
    pool = editing.unused_pool(project.id)
    assert len(pool) == 1


def test_assign_allows_reusing_photo(tmp_path: Path) -> None:
    database, _distribution, editing, project = _setup(
        tmp_path, page_count=1, photo_count=2, slots_per_page=2
    )
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        photos = connection.execute("SELECT id FROM photos ORDER BY id").fetchall()

    editing.assign_to_empty_slot(project.id, page.id, layout.slots[0].id, photos[0]["id"])
    editing.assign_to_empty_slot(project.id, page.id, layout.slots[1].id, photos[0]["id"])

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT photo_id FROM assignments WHERE project_id = ? ORDER BY slot_id",
            (project.id,),
        ).fetchall()
    assert [row["photo_id"] for row in rows] == [photos[0]["id"], photos[0]["id"]]


def test_assign_rejects_occupied_slot(tmp_path: Path) -> None:
    database, _distribution, editing, project = _setup(
        tmp_path, page_count=1, photo_count=2, slots_per_page=2
    )
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        photos = connection.execute("SELECT id FROM photos ORDER BY id").fetchall()

    editing.assign_to_empty_slot(project.id, page.id, layout.slots[0].id, photos[0]["id"])
    with pytest.raises(DuplicateSlotAssignmentError):
        editing.assign_to_empty_slot(project.id, page.id, layout.slots[0].id, photos[1]["id"])


def test_remove_returns_photo_to_pool(tmp_path: Path) -> None:
    database, _distribution, editing, project = _setup(
        tmp_path, page_count=1, photo_count=2, slots_per_page=2
    )
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        photos = connection.execute("SELECT id FROM photos ORDER BY id").fetchall()

    editing.assign_to_empty_slot(project.id, page.id, layout.slots[0].id, photos[0]["id"])
    assert len(editing.unused_pool(project.id)) == 1
    editing.remove(project.id, page.id, layout.slots[0].id)
    assert len(editing.unused_pool(project.id)) == 2


def test_swap_moves_photos_between_slots(tmp_path: Path) -> None:
    database, _distribution, editing, project = _setup(
        tmp_path, page_count=1, photo_count=2, slots_per_page=2
    )
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        photos = connection.execute("SELECT id FROM photos ORDER BY id").fetchall()

    editing.assign_to_empty_slot(project.id, page.id, layout.slots[0].id, photos[0]["id"])
    editing.assign_to_empty_slot(project.id, page.id, layout.slots[1].id, photos[1]["id"])
    editing.swap(project.id, page.id, layout.slots[0].id, layout.slots[1].id)

    with database.connect() as connection:
        assignments = {
            row["slot_id"]: row["photo_id"]
            for row in connection.execute(
                "SELECT slot_id, photo_id FROM assignments WHERE page_id = ?",
                (page.id,),
            ).fetchall()
        }
    assert assignments[layout.slots[0].id] == photos[1]["id"]
    assert assignments[layout.slots[1].id] == photos[0]["id"]


def test_date_aware_proposal_matches_weeks(tmp_path: Path) -> None:
    start = datetime(2027, 1, 4)
    database, distribution, _editing, project = _setup(
        tmp_path, page_count=1, photo_count=2, slots_per_page=2, start_date=start
    )
    proposal = distribution.propose(project.id, strategy="date_aware")
    assert len(proposal.pages) == 1
