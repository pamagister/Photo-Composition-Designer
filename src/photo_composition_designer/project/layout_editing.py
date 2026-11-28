"""Explicit layout selection and assignment mapping operations."""

from __future__ import annotations

from dataclasses import dataclass

from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.layouts.loader import (
    AUTO_LAYOUT_KEY,
    LayoutTemplate,
    load_catalogue,
)
from photo_composition_designer.project.auto_layout_service import AutomaticLayoutService
from photo_composition_designer.project.layout_models import LayoutChangePreview
from photo_composition_designer.project.models import LayoutSlot
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


class LayoutEditingService:
    """Preview and apply explicit changes between persisted page layouts."""

    def __init__(
        self,
        database: WorkspaceDatabase,
        automatic_layout: AutomaticLayoutService,
    ) -> None:
        self._database = database
        self._automatic_layout = automatic_layout

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
        if layout_key == AUTO_LAYOUT_KEY:
            return self._automatic_layout.preview_layout_change(project_id, page_id)
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
        if layout_key == AUTO_LAYOUT_KEY:
            return self._automatic_layout.change_to_automatic_layout(project_id, page_id)
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
