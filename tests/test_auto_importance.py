"""Tests for content-aware importance weighting in automatic layouts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.editing import PageEditingService
from photo_composition_designer.project.importance import (
    IMPORTANT_CLASSES,
    ImportanceScorer,
)
from photo_composition_designer.project.inventory import InventoryService
from photo_composition_designer.project.models import PhotoAsset
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
)
from photo_composition_designer.project.services import ProjectService
from photo_composition_designer.render.object_detector import Detection

#: A small seed layout with enough slots for the service tests.
_SEED_LAYOUT = "tiles_4_rows_5col"


class FakeDetector:
    """Return detections based on the top-left pixel colour of an image."""

    def __init__(self, classes_by_colour: dict[tuple[int, int, int], list[str]]) -> None:
        self._classes_by_colour = classes_by_colour
        self.calls = 0

    def detect(self, image: Image.Image) -> list[Detection]:
        self.calls += 1
        colour = image.convert("RGB").getpixel((0, 0))
        return [
            Detection(class_name=name, confidence=0.8, bbox=(0.0, 0.0, 1.0, 1.0))
            for name in self._classes_by_colour.get(colour, [])
        ]


class NeutralDetector:
    """A detector that never finds anything."""

    def __init__(self) -> None:
        self.calls = 0

    def detect(self, image: Image.Image) -> list[Detection]:
        self.calls += 1
        return []


def _write_photo(path: Path, colour: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # PNG keeps the exact test colour; JPEG would shift it and break the fake
    # detector's pixel lookup.
    Image.new("RGB", (1600, 1200), colour).save(path, format="PNG")


def _write_and_load(tmp_path: Path, colour: tuple[int, int, int]) -> PhotoAsset:
    """Write one source photo and return a matching inventory row."""
    database = WorkspaceDatabase(tmp_path / "scorer.sqlite3")
    project = ProjectService(database).create_project(
        name="Scorer",
        page_count=1,
        start_date=datetime(2027, 1, 4),
    )
    source = tmp_path / "source"
    _write_photo(source / "photo.jpg", colour)
    inventory = InventoryService(database)
    inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=1)
    with database.connect() as connection:
        return PhotoRepository(connection).list(project.id)[0]


def _seed_project(
    tmp_path: Path,
    *,
    colours: list[tuple[int, int, int]],
    image_score_factor: float,
) -> tuple[WorkspaceDatabase, int, list[int], list[int], list[int]]:
    database = WorkspaceDatabase(tmp_path / "workspace.sqlite3")
    project = ProjectService(database).create_project(
        name="Importance",
        page_count=1,
        start_date=datetime(2027, 1, 4),
        output_profile={"layout": {"image_score_factor": image_score_factor}},
    )
    source = tmp_path / "source"
    for index, colour in enumerate(colours):
        _write_photo(source / f"photo_{index:02d}.jpg", colour)
    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    editing = PageEditingService(database)
    with database.connect() as connection:
        page = PageRepository(connection).list(project.id)[0]
        photo_ids = [row["id"] for row in connection.execute("SELECT id FROM photos ORDER BY id")]
    editing.change_layout(project.id, page.id, _SEED_LAYOUT)
    with database.connect() as connection:
        page = PageRepository(connection).get(page.id)
        assert page is not None and page.layout_id is not None
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        assert layout is not None
        slot_ids = [slot.id for slot in layout.slots]
    return database, project.id, page.id, photo_ids, slot_ids


def _assign(
    editing: PageEditingService,
    project_id: int,
    page_id: int,
    photo_ids: list[int],
    slot_ids: list[int],
) -> None:
    for photo_id, slot_id in zip(photo_ids, slot_ids, strict=False):
        editing.assign_to_empty_slot(project_id, page_id, slot_id, photo_id)


def _layout_and_assignments(database: WorkspaceDatabase, page_id: int):
    with database.connect() as connection:
        page = PageRepository(connection).get(page_id)
        assert page is not None and page.layout_id is not None
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        assert layout is not None
        assignments = AssignmentRepository(connection).list_by_page(page_id)
        return layout, assignments


def test_importance_scores_person(tmp_path: Path) -> None:
    photo = _write_and_load(tmp_path, (200, 10, 10))
    detector = FakeDetector({(200, 10, 10): ["person"]})

    value = ImportanceScorer(detector, 2.0).for_photo(photo, tmp_path / "source" / "photo.jpg")

    assert value == pytest.approx(1.0 + 0.8 * 2.0)


def test_importance_scores_sum_and_cap_multiple_detections(tmp_path: Path) -> None:
    photo = _write_and_load(tmp_path, (200, 10, 10))
    detector = FakeDetector({(200, 10, 10): ["person", "cat"]})

    uncapped = ImportanceScorer(detector, 1.0, cap=10.0).for_photo(
        photo, tmp_path / "source" / "photo.jpg"
    )
    capped = ImportanceScorer(detector, 1.0, cap=0.8).for_photo(
        photo, tmp_path / "source" / "photo.jpg"
    )

    assert uncapped == pytest.approx(2.6)
    assert capped == pytest.approx(1.8)


def test_importance_ignores_unimportant_classes(tmp_path: Path) -> None:
    photo = _write_and_load(tmp_path, (200, 10, 10))
    detector = FakeDetector({(200, 10, 10): ["car", "bottle"]})

    value = ImportanceScorer(detector, 2.0).for_photo(photo, tmp_path / "source" / "photo.jpg")

    assert value == pytest.approx(1.0)


def test_importance_neutral_without_detector_or_factor(tmp_path: Path) -> None:
    photo = _write_and_load(tmp_path, (200, 10, 10))
    detector = FakeDetector({(200, 10, 10): ["person"]})

    without_detector = ImportanceScorer(None, 2.0).for_photo(
        photo, tmp_path / "source" / "photo.jpg"
    )
    zero_factor = ImportanceScorer(detector, 0.0).for_photo(
        photo, tmp_path / "source" / "photo.jpg"
    )

    assert without_detector == pytest.approx(1.0)
    assert zero_factor == pytest.approx(1.0)
    assert detector.calls == 0


def test_importance_cache_uses_digest(tmp_path: Path) -> None:
    photo = _write_and_load(tmp_path, (200, 10, 10))
    detector = FakeDetector({(200, 10, 10): ["person"]})
    scorer = ImportanceScorer(detector, 2.0)

    first = scorer.for_photo(photo, tmp_path / "source" / "photo.jpg")
    second = scorer.for_photo(photo, tmp_path / "source" / "photo.jpg")

    assert first == pytest.approx(second)
    assert detector.calls == 1


def test_importance_neutral_when_source_file_is_missing(tmp_path: Path) -> None:
    photo = _write_and_load(tmp_path, (200, 10, 10))
    detector = FakeDetector({(200, 10, 10): ["person"]})

    value = ImportanceScorer(detector, 2.0).for_photo(photo, tmp_path / "missing.jpg")

    assert value == pytest.approx(1.0)
    assert detector.calls == 0


def test_important_classes_match_product_expectation() -> None:
    assert IMPORTANT_CLASSES == {"person", "cat", "dog", "horse", "cow", "bird"}


def test_high_importance_photo_gets_a_larger_cell(tmp_path: Path) -> None:
    database, project_id, page_id, photo_ids, slot_ids = _seed_project(
        tmp_path,
        colours=[(200, 10, 10), (10, 10, 200)],
        image_score_factor=2.0,
    )
    try:
        editing = PageEditingService(
            database,
            object_detector=FakeDetector({(200, 10, 10): ["person"]}),
        )
        _assign(editing, project_id, page_id, photo_ids[:2], slot_ids)

        editing.change_layout(project_id, page_id, "auto")

        layout, assignments = _layout_and_assignments(database, page_id)
        by_photo = {assignment.photo_id: assignment for assignment in assignments}
        high_slot = next(slot for slot in layout.slots if slot.id == by_photo[photo_ids[0]].slot_id)
        low_slot = next(slot for slot in layout.slots if slot.id == by_photo[photo_ids[1]].slot_id)
        assert high_slot.width > low_slot.width
    finally:
        database.close()


def test_regenerate_auto_layouts_reapplies_importance(tmp_path: Path) -> None:
    database, project_id, page_id, photo_ids, slot_ids = _seed_project(
        tmp_path,
        colours=[(200, 10, 10), (10, 10, 200)],
        image_score_factor=2.0,
    )
    try:
        scored = PageEditingService(
            database,
            object_detector=FakeDetector({(200, 10, 10): ["person"]}),
        )
        _assign(scored, project_id, page_id, photo_ids[:2], slot_ids)
        scored.change_layout(project_id, page_id, "auto")
        first_layout, first_assignments = _layout_and_assignments(database, page_id)

        regenerated = scored.regenerate_auto_layouts(
            project_id,
            object_detector=NeutralDetector(),
        )

        assert regenerated == 1
        layout, assignments = _layout_and_assignments(database, page_id)
        assert layout.id != first_layout.id
        by_photo = {assignment.photo_id: assignment for assignment in assignments}
        high_slot = next(slot for slot in layout.slots if slot.id == by_photo[photo_ids[0]].slot_id)
        low_slot = next(slot for slot in layout.slots if slot.id == by_photo[photo_ids[1]].slot_id)
        assert high_slot.width == pytest.approx(low_slot.width)
        assert {item.photo_id for item in first_assignments} == set(by_photo)
    finally:
        database.close()
