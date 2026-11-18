"""Page editing services: assign, remove, replace, swap and unused pool.

All operations are transactional and enforce the project invariants: a photo
is assigned at most once per project, and a slot holds at most one photo.
Every mutation increments the affected page's render revision so cached
previews are invalidated.
"""

from __future__ import annotations

from photo_composition_designer.core.errors import (
    DuplicatePhotoAssignmentError,
    DuplicateSlotAssignmentError,
    ProjectError,
)
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.models import PhotoAsset
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
)


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
            DuplicatePhotoAssignmentError: If the photo is already assigned.
            DuplicateSlotAssignmentError: If the slot is occupied.
            ProjectError: If the page, slot or layout is invalid.
        """
        with self._database.transaction() as connection:
            page, layout = self._page_and_layout(connection, page_id)
            slot_keys = {slot.id for slot in layout.slots}
            if slot_id not in slot_keys:
                raise ProjectError(f"slot {slot_id} does not belong to page {page_id} layout")

            assignments = AssignmentRepository(connection)
            if any(a.photo_id == photo_id for a in assignments.list(project_id)):
                raise DuplicatePhotoAssignmentError(
                    f"photo {photo_id} is already assigned in project {project_id}"
                )
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
            if any(
                a.photo_id == photo_id and a.slot_id != slot_id
                for a in assignments.list(project_id)
            ):
                raise DuplicatePhotoAssignmentError(
                    f"photo {photo_id} is assigned to a different slot"
                )

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

    def unused_pool(self, project_id: int) -> list[PhotoAsset]:
        """Return photos that are not assigned to any slot in the project."""
        with self._database.transaction() as connection:
            assigned = {a.photo_id for a in AssignmentRepository(connection).list(project_id)}
            return [
                photo
                for photo in PhotoRepository(connection).list(project_id, available_only=True)
                if photo.id not in assigned
            ]
