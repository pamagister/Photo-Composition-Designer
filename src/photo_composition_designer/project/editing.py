"""Page editing services: assign, remove, replace, swap and unused pool.

All operations are transactional and enforce the project invariants: a photo
may be assigned repeatedly, and a slot holds at most one photo.
Every mutation increments the affected page's render revision so cached
previews are invalidated.
"""

from __future__ import annotations

from photo_composition_designer.core.errors import (
    DuplicateSlotAssignmentError,
    ProjectError,
)
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.auto_layout_service import AutomaticLayoutService
from photo_composition_designer.project.layout_editing import LayoutEditingService
from photo_composition_designer.project.layout_models import LayoutChangePreview
from photo_composition_designer.project.models import PhotoAsset
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
)
from photo_composition_designer.render.object_detector import ObjectDetector


class PageEditingService:
    """Coordinate page assignment and layout-editing operations."""

    def __init__(
        self,
        database: WorkspaceDatabase,
        object_detector: ObjectDetector | None = None,
    ) -> None:
        self._database = database
        self._automatic_layout = AutomaticLayoutService(database, object_detector)
        self._layout_editing = LayoutEditingService(database, self._automatic_layout)

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

    def populate(self, project_id: int, page_id: int) -> int:
        """Assign unused available photos to the page's empty slots.

        Slots are filled in layout order with photos that are available and not
        assigned anywhere in the project, in inventory (``relative_path``) order.
        Occupied slots are left untouched. Returns the number of photos assigned.
        """
        with self._database.transaction() as connection:
            page, layout = self._page_and_layout(connection, page_id)
            assignments = AssignmentRepository(connection)
            occupied_slots = {
                assignment.slot_id for assignment in assignments.list_by_page(page_id)
            }
            empty_slots = sorted(
                (slot for slot in layout.slots if slot.id not in occupied_slots),
                key=lambda slot: slot.position,
            )
            if not empty_slots:
                return 0

            used_photo_ids = {
                assignment.photo_id for assignment in assignments.list_by_project(project_id)
            }
            candidates = [
                photo
                for photo in PhotoRepository(connection).list(project_id, available_only=True)
                if photo.id not in used_photo_ids
            ]
            pairs = list(zip(empty_slots, candidates, strict=False))
            for slot, photo in pairs:
                assignments.assign(
                    project_id=project_id,
                    page_id=page_id,
                    slot_id=slot.id,
                    photo_id=photo.id,
                )
            if pairs:
                PageRepository(connection).increment_revision(page_id)
            return len(pairs)

    def assign_selected(
        self,
        project_id: int,
        page_id: int,
        photo_ids: list[int] | tuple[int, ...],
        *,
        slot_id: int | None = None,
    ) -> int:
        """Assign the given photos to the page's empty slots in the given order.

        Photos are placed in slot order, skipping unavailable photos. A photo
        already used elsewhere may be assigned again. Occupied slots are left
        untouched unless ``slot_id`` is supplied, in which case the first
        eligible photo is assigned there, replacing its current photo. Remaining
        photos fill empty slots in order. The revision increments only when at
        least one assignment was made. Returns the number assigned.
        """
        with self._database.transaction() as connection:
            page, layout = self._page_and_layout(connection, page_id)
            layout_slot_ids = {slot.id for slot in layout.slots}
            if slot_id is not None and slot_id not in layout_slot_ids:
                raise ProjectError(f"slot {slot_id} does not belong to page {page_id} layout")

            assignments = AssignmentRepository(connection)
            page_assignments = assignments.list_by_page(page_id)
            occupied_slots = {assignment.slot_id for assignment in page_assignments}
            empty_slots = sorted(
                (
                    slot
                    for slot in layout.slots
                    if slot.id not in occupied_slots and slot.id != slot_id
                ),
                key=lambda slot: slot.position,
            )
            if not photo_ids:
                return 0

            photos = PhotoRepository(connection)
            candidates: list[int] = []
            seen: set[int] = set()
            for photo_id in photo_ids:
                if photo_id in seen:
                    continue
                photo = photos.get(photo_id)
                if photo is None or not photo.available:
                    continue
                seen.add(photo_id)
                candidates.append(photo_id)

            pairs: list[tuple[int, int]] = []
            if slot_id is not None and candidates:
                if slot_id in occupied_slots:
                    assignments.remove_by_page_slot(page_id, slot_id)
                pairs.append((slot_id, candidates.pop(0)))
            pairs.extend(
                (slot.id, photo_id) for slot, photo_id in zip(empty_slots, candidates, strict=False)
            )
            for target_slot_id, photo_id in pairs:
                assignments.assign(
                    project_id=project_id,
                    page_id=page_id,
                    slot_id=target_slot_id,
                    photo_id=photo_id,
                )
            if pairs:
                PageRepository(connection).increment_revision(page_id)
            return len(pairs)

    def remove(self, project_id: int, page_id: int, slot_id: int) -> bool:
        """Clear a slot and return the photo to the unused pool."""
        with self._database.transaction() as connection:
            assignments = AssignmentRepository(connection)
            removed = assignments.remove_by_page_slot(page_id, slot_id)
            if removed:
                PageRepository(connection).increment_revision(page_id)
            return removed

    def clear_page_assignments(self, project_id: int, page_id: int) -> int:
        """Remove all assignments from one page and return the number removed.

        The page layout is kept. The page render revision is incremented when at
        least one assignment was removed so cached previews are invalidated.
        """
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            removed = AssignmentRepository(connection).clear_for_page(page_id)
            if removed:
                PageRepository(connection).increment_revision(page_id)
            return removed

    def clear_project_assignments(self, project_id: int) -> int:
        """Remove every assignment in a project and return the number removed.

        Every page render revision is incremented when assignments were removed
        so cached previews are invalidated across the project.
        """
        with self._database.transaction() as connection:
            if ProjectRepository(connection).get(project_id) is None:
                raise ProjectError(f"project {project_id} does not exist")
            removed = AssignmentRepository(connection).clear_for_project(project_id)
            if removed:
                PageRepository(connection).increment_revisions(project_id)
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

    def auto_add(self, project_id: int, page_id: int, photo_id: int) -> bool:
        """Add a photo to an automatic page."""
        return self._automatic_layout.auto_add(project_id, page_id, photo_id)

    def auto_add_many(
        self,
        project_id: int,
        page_id: int,
        photo_ids: list[int] | tuple[int, ...],
    ) -> tuple[int, bool]:
        """Add several photos to an automatic page in one transaction."""
        return self._automatic_layout.auto_add_many(project_id, page_id, photo_ids)

    def auto_fill_unused(
        self,
        project_id: int,
        page_id: int,
        limit: int,
    ) -> tuple[int, bool]:
        """Fill an automatic page with unused photos."""
        return self._automatic_layout.auto_fill_unused(project_id, page_id, limit)

    def uses_auto_layout(self, project_id: int, page_id: int) -> bool:
        """Return whether a page currently uses an automatic layout."""
        return self._automatic_layout.uses_auto_layout(project_id, page_id)

    def auto_reflow(self, project_id: int, page_id: int) -> bool:
        """Regenerate an automatic layout for its current assignments."""
        return self._automatic_layout.auto_reflow(project_id, page_id)

    def auto_remove_empty(self, project_id: int, page_id: int) -> bool:
        """Remove empty slots from an automatic layout."""
        return self._automatic_layout.auto_remove_empty(project_id, page_id)

    def regenerate_auto_layouts(
        self,
        project_id: int,
        *,
        object_detector: ObjectDetector | None = None,
    ) -> int:
        """Regenerate automatic layouts after project data changes."""
        return self._automatic_layout.regenerate_auto_layouts(
            project_id, object_detector=object_detector
        )

    def reset_all_layouts_to_auto(
        self,
        project_id: int,
        *,
        preserve_assignments: bool = True,
    ) -> int:
        """Reset every page to an automatic layout."""
        return self._automatic_layout.reset_all_layouts_to_auto(
            project_id, preserve_assignments=preserve_assignments
        )

    @staticmethod
    def _reset_layouts_in_transaction(
        connection,
        project_id: int,
        *,
        preserve_assignments: bool = True,
    ) -> int:
        """Reset layouts inside a caller-owned transaction."""
        return AutomaticLayoutService._reset_layouts_in_transaction(
            connection, project_id, preserve_assignments=preserve_assignments
        )

    def plan_layout_change(
        self,
        project_id: int,
        page_id: int,
        layout_key: str,
    ) -> LayoutChangePreview:
        """Preview a layout change without mutating the project."""
        return self._layout_editing.plan_layout_change(project_id, page_id, layout_key)

    def change_layout(
        self,
        project_id: int,
        page_id: int,
        layout_key: str,
    ) -> LayoutChangePreview:
        """Apply a layout change while preserving assignments that fit."""
        return self._layout_editing.change_layout(project_id, page_id, layout_key)

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
            if page.description == description:
                return
            PageRepository(connection).update_description(page_id, description)

    def set_local_overrides(
        self,
        project_id: int,
        page_id: int,
        *,
        hide_local_map: bool,
        hide_calendar_strip: bool,
        hide_description: bool,
        center_description: bool | None = None,
    ) -> None:
        """Set the per-page overrides for map, calendar strip and description."""
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            if (
                page.hide_local_map == hide_local_map
                and page.hide_calendar_strip == hide_calendar_strip
                and page.hide_description == hide_description
                and page.center_description == center_description
            ):
                return
            PageRepository(connection).set_local_overrides(
                page_id,
                hide_local_map=hide_local_map,
                hide_calendar_strip=hide_calendar_strip,
                hide_description=hide_description,
                center_description=center_description,
            )

    def unused_pool(self, project_id: int) -> list[PhotoAsset]:
        """Return photos that are not assigned to any slot in the project."""
        with self._database.transaction() as connection:
            assigned = {a.photo_id for a in AssignmentRepository(connection).list(project_id)}
            return [
                photo
                for photo in PhotoRepository(connection).list(project_id, available_only=True)
                if photo.id not in assigned
            ]
