"""Page editing services: assign, remove, replace, swap and unused pool.

All operations are transactional and enforce the project invariants: a photo
may be assigned repeatedly, and a slot holds at most one photo.
Every mutation increments the affected page's render revision so cached
previews are invalidated.
"""

from __future__ import annotations

from dataclasses import dataclass

from photo_composition_designer.core.errors import (
    DuplicateSlotAssignmentError,
    ProjectError,
)
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.layouts.loader import LayoutTemplate, load_catalogue
from photo_composition_designer.project.models import LayoutSlot, PhotoAsset
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
)


@dataclass(frozen=True)
class _SlotRect:
    """Normalized slot geometry used for deterministic layout mapping."""

    slot_id: int
    key: str
    x: float
    y: float
    width: float
    height: float
    position: int


@dataclass(frozen=True)
class LayoutChangePreview:
    """Result of previewing or applying a layout change."""

    page_id: int
    layout_key: str
    layout_name: str
    slot_count: int
    preserved: tuple[tuple[int, str], ...]
    displaced: tuple[PhotoAsset, ...]

    @property
    def has_displaced(self) -> bool:
        return bool(self.displaced)


def _rects_from_template(template: LayoutTemplate) -> list[_SlotRect]:
    """Convert a layout template into normalized slot rectangles."""
    return [
        _SlotRect(
            slot_id=-1,
            key=slot.key,
            x=slot.x,
            y=slot.y,
            width=slot.width,
            height=slot.height,
            position=index,
        )
        for index, slot in enumerate(template.slots)
    ]


def _rects_from_layout(slots: list[LayoutSlot]) -> list[_SlotRect]:
    """Convert persisted layout slots into normalized slot rectangles."""
    return [
        _SlotRect(
            slot_id=slot.id,
            key=slot.slot_key,
            x=slot.x,
            y=slot.y,
            width=slot.width,
            height=slot.height,
            position=slot.position,
        )
        for slot in slots
    ]


class PageEditingService:
    """Mutate slot assignments for a project."""

    def __init__(self, database: WorkspaceDatabase) -> None:
        self._database = database

    def _page_and_layout(self, connection, page_id: int):
        page = PageRepository(connection).get(page_id)
        if page is None:
            raise ProjectError(f"page {page_id} does not exist")
        if page.layout_id is None:
            raise ProjectError(f"page {page_id} has no layout")
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        if layout is None:
            raise ProjectError(f"page {page_id} layout is missing")
        return page, layout

    def assign_to_empty_slot(
        self,
        project_id: int,
        page_id: int,
        slot_id: int,
        photo_id: int,
    ) -> None:
        """Assign a photo to an empty slot.

        Raises:
            DuplicateSlotAssignmentError: If the slot is occupied.
            ProjectError: If the page, slot or layout is invalid.
        """
        with self._database.transaction() as connection:
            page, layout = self._page_and_layout(connection, page_id)
            slot_keys = {slot.id for slot in layout.slots}
            if slot_id not in slot_keys:
                raise ProjectError(f"slot {slot_id} does not belong to page {page_id} layout")

            assignments = AssignmentRepository(connection)
            if any(a.slot_id == slot_id for a in assignments.list_by_page(page_id)):
                raise DuplicateSlotAssignmentError(
                    f"slot {slot_id} on page {page_id} is already occupied"
                )

            assignments.assign(
                project_id=project_id,
                page_id=page_id,
                slot_id=slot_id,
                photo_id=photo_id,
            )
            PageRepository(connection).increment_revision(page_id)

    def remove(self, project_id: int, page_id: int, slot_id: int) -> bool:
        """Clear a slot and return the photo to the unused pool."""
        with self._database.transaction() as connection:
            assignments = AssignmentRepository(connection)
            removed = assignments.remove_by_page_slot(page_id, slot_id)
            if removed:
                PageRepository(connection).increment_revision(page_id)
            return removed

    def replace(self, project_id: int, page_id: int, slot_id: int, photo_id: int) -> None:
        """Replace the photo in an occupied slot.

        The replaced photo returns to the unused pool automatically because the
        unused pool is derived from assignments.
        """
        with self._database.transaction() as connection:
            page, layout = self._page_and_layout(connection, page_id)
            slot_keys = {slot.id for slot in layout.slots}
            if slot_id not in slot_keys:
                raise ProjectError(f"slot {slot_id} does not belong to page {page_id} layout")

            assignments = AssignmentRepository(connection)
            assignments.remove_by_page_slot(page_id, slot_id)
            assignments.assign(
                project_id=project_id,
                page_id=page_id,
                slot_id=slot_id,
                photo_id=photo_id,
            )
            PageRepository(connection).increment_revision(page_id)

    def swap(
        self,
        project_id: int,
        page_id: int,
        slot_a: int,
        slot_b: int,
    ) -> None:
        """Swap the photos in two slots on the same page.

        Both slots must be on ``page_id``. Swapping an empty slot moves the
        photo to the empty slot and leaves the other empty.
        """
        with self._database.transaction() as connection:
            page, layout = self._page_and_layout(connection, page_id)
            slot_keys = {slot.id for slot in layout.slots}
            if slot_a not in slot_keys or slot_b not in slot_keys:
                raise ProjectError("both slots must belong to the page layout")
            if slot_a == slot_b:
                return

            assignments = AssignmentRepository(connection)
            by_slot = {a.slot_id: a for a in assignments.list_by_page(page_id)}
            a = by_slot.get(slot_a)
            b = by_slot.get(slot_b)

            if a is not None:
                assignments.remove(a.id)
            if b is not None:
                assignments.remove(b.id)

            if b is not None:
                assignments.assign(
                    project_id=project_id,
                    page_id=page_id,
                    slot_id=slot_a,
                    photo_id=b.photo_id,
                )
            if a is not None:
                assignments.assign(
                    project_id=project_id,
                    page_id=page_id,
                    slot_id=slot_b,
                    photo_id=a.photo_id,
                )
            PageRepository(connection).increment_revision(page_id)

    @staticmethod
    def _resolve_template(layout_key: str) -> LayoutTemplate:
        """Return a layout template from the catalogue or raise a domain error."""
        template = load_catalogue().get(layout_key)
        if template is None:
            raise ProjectError(f"layout {layout_key!r} does not exist")
        return template

    @staticmethod
    def _ensure_layout(connection, template: LayoutTemplate):
        """Return the persisted layout snapshot for a template, creating it once."""
        repository = LayoutRepository(connection)
        existing = repository.get(template.key, template.version)
        if existing is not None:
            return existing
        slots = [
            LayoutSlot(
                id=0,
                layout_id=0,
                slot_key=slot.key,
                position=index,
                x=slot.x,
                y=slot.y,
                width=slot.width,
                height=slot.height,
                z_index=0,
                crop_mode=slot.crop_mode,
            )
            for index, slot in enumerate(template.slots)
        ]
        return repository.add(template.key, template.version, template.name, slots)

    @staticmethod
    def _plan_mapping(
        assignments: list,
        old_slots: list[LayoutSlot],
        new_slots: list[_SlotRect],
    ) -> tuple[list[tuple[object, _SlotRect]], list[object]]:
        """Map existing assignments onto new slots by nearest normalized center."""
        old_by_id = {slot.id: slot for slot in old_slots}
        available = sorted(new_slots, key=lambda slot: (slot.position, slot.key))
        pairs: list[tuple[object, _SlotRect]] = []
        displaced: list[object] = []

        ordered = sorted(
            (a for a in assignments if a.slot_id in old_by_id),
            key=lambda a: old_by_id[a.slot_id].position,
        )
        for assignment in ordered:
            old_slot = old_by_id[assignment.slot_id]
            center_x = old_slot.x + old_slot.width / 2
            center_y = old_slot.y + old_slot.height / 2
            if not available:
                displaced.append(assignment)
                continue
            best = min(
                available,
                key=lambda slot: (
                    (slot.x + slot.width / 2 - center_x) ** 2
                    + (slot.y + slot.height / 2 - center_y) ** 2,
                    slot.position,
                ),
            )
            available.remove(best)
            pairs.append((assignment, best))

        displaced.extend(a for a in assignments if a.slot_id not in old_by_id)
        return pairs, displaced

    def plan_layout_change(
        self,
        project_id: int,
        page_id: int,
        layout_key: str,
    ) -> LayoutChangePreview:
        """Preview a layout change without mutating the project."""
        template = self._resolve_template(layout_key)
        new_slots = _rects_from_template(template)
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            old_layout = (
                LayoutRepository(connection).get_by_id(page.layout_id)
                if page.layout_id is not None
                else None
            )
            old_slots = old_layout.slots if old_layout is not None else []
            assignments = AssignmentRepository(connection).list_by_page(page_id)
            pairs, displaced = self._plan_mapping(assignments, old_slots, new_slots)
            photos = PhotoRepository(connection)
            displaced_photos = tuple(
                photo for photo in (photos.get(a.photo_id) for a in displaced) if photo is not None
            )
            preserved = tuple((a.photo_id, rect.key) for a, rect in pairs)
            return LayoutChangePreview(
                page_id=page_id,
                layout_key=template.key,
                layout_name=template.name,
                slot_count=len(new_slots),
                preserved=preserved,
                displaced=displaced_photos,
            )

    def change_layout(
        self,
        project_id: int,
        page_id: int,
        layout_key: str,
    ) -> LayoutChangePreview:
        """Apply a layout change atomically, preserving as many assignments as fit."""
        template = self._resolve_template(layout_key)
        with self._database.transaction() as connection:
            page_repository = PageRepository(connection)
            page = page_repository.get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")

            layout = self._ensure_layout(connection, template)
            old_layout = (
                LayoutRepository(connection).get_by_id(page.layout_id)
                if page.layout_id is not None
                else None
            )
            old_slots = old_layout.slots if old_layout is not None else []
            assignments = AssignmentRepository(connection)
            existing = assignments.list_by_page(page_id)
            pairs, displaced = self._plan_mapping(
                existing, old_slots, _rects_from_layout(layout.slots)
            )

            page_repository.set_layout(page_id, layout.id, layout.version)
            for assignment in existing:
                assignments.remove(assignment.id)
            for assignment, rect in pairs:
                assignments.assign(
                    project_id=project_id,
                    page_id=page_id,
                    slot_id=rect.slot_id,
                    photo_id=assignment.photo_id,
                    crop_zoom=assignment.crop_zoom,
                    crop_focus_x=assignment.crop_focus_x,
                    crop_focus_y=assignment.crop_focus_y,
                )

            photos = PhotoRepository(connection)
            displaced_photos = tuple(
                photo for photo in (photos.get(a.photo_id) for a in displaced) if photo is not None
            )
            return LayoutChangePreview(
                page_id=page_id,
                layout_key=template.key,
                layout_name=template.name,
                slot_count=len(layout.slots),
                preserved=tuple((a.photo_id, rect.key) for a, rect in pairs),
                displaced=displaced_photos,
            )

    def set_crop(
        self,
        project_id: int,
        page_id: int,
        slot_id: int,
        *,
        crop_zoom: float = 1.0,
        crop_focus_x: float = 0.5,
        crop_focus_y: float = 0.5,
    ) -> None:
        """Update the crop zoom and focal point for one assignment."""
        if crop_zoom < 1.0:
            raise ProjectError("crop_zoom must be at least 1.0")
        if not 0.0 <= crop_focus_x <= 1.0 or not 0.0 <= crop_focus_y <= 1.0:
            raise ProjectError("crop focus values must be between 0 and 1")

        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            assignment = next(
                (
                    item
                    for item in AssignmentRepository(connection).list_by_page(page_id)
                    if item.slot_id == slot_id
                ),
                None,
            )
            if assignment is None:
                raise ProjectError(f"slot {slot_id} on page {page_id} has no assignment")

            AssignmentRepository(connection).update_crop(
                assignment.id,
                crop_zoom=crop_zoom,
                crop_focus_x=crop_focus_x,
                crop_focus_y=crop_focus_y,
            )
            PageRepository(connection).increment_revision(page_id)

    def set_description(self, project_id: int, page_id: int, description: str) -> None:
        """Update the page description and invalidate its render revision."""
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            PageRepository(connection).update_description(page_id, description)

    def unused_pool(self, project_id: int) -> list[PhotoAsset]:
        """Return photos that are not assigned to any slot in the project."""
        with self._database.transaction() as connection:
            assigned = {a.photo_id for a in AssignmentRepository(connection).list(project_id)}
            return [
                photo
                for photo in PhotoRepository(connection).list(project_id, available_only=True)
                if photo.id not in assigned
            ]
