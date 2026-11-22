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
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.layouts.auto_layout import AutoPhoto, AutoSlot, build_auto_layout
from photo_composition_designer.layouts.loader import (
    AUTO_LAYOUT_KEY,
    AUTO_LAYOUT_NAME,
    LayoutTemplate,
    load_catalogue,
)
from photo_composition_designer.project.importance import ImportanceScorer
from photo_composition_designer.project.models import LayoutSlot, PhotoAsset, PhotoAssignment
from photo_composition_designer.project.rendering import (
    collage_aspect_for_page,
    profile_from_project,
)
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    LayoutRepository,
    PageRepository,
    PhotoRepository,
    ProjectRepository,
)
from photo_composition_designer.render.object_detector import ObjectDetector


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


def _order_pairs_by_engine(
    pairs: list[tuple[PhotoAssignment, PhotoAsset]],
    importance: list[float] | None = None,
) -> tuple[
    list[tuple[PhotoAssignment, PhotoAsset]],
    tuple[AutoPhoto, ...],
]:
    """Order assignment pairs the way the automatic engine groups photos.

    The engine orders photos by orientation (portrait, square, landscape) and
    keeps the input order inside an orientation class. The returned pairs are
    aligned with the returned engine photos, so ``pairs[i]`` is the assignment
    that should occupy ``auto_<i>``. ``importance`` is aligned with ``pairs``
    and defaults to the neutral value.
    """
    engine_photos = [
        AutoPhoto(
            key=str(photo.id),
            width=photo.width,
            height=photo.height,
            importance=importance[index] if importance is not None else 1.0,
        )
        for index, (_, photo) in enumerate(pairs)
    ]
    indexed = sorted(
        enumerate(engine_photos),
        key=lambda pair: (round(pair[1].aspect, 2), pair[0]),
    )
    ordered_pairs = [pairs[index] for index, _ in indexed]
    ordered_photos = tuple(photo for _, photo in indexed)
    return ordered_pairs, ordered_photos


class PageEditingService:
    """Mutate slot assignments for a project."""

    def __init__(
        self,
        database: WorkspaceDatabase,
        object_detector: ObjectDetector | None = None,
    ) -> None:
        self._database = database
        self._object_detector = object_detector
        self._importance_scorers: dict[float, ImportanceScorer] = {}

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
    def _auto_pairs(connection, page) -> list[tuple[PhotoAssignment, PhotoAsset]]:
        """Return a page's valid assignments ordered by their current slot.

        Assignments are ordered by the position of their current slot so the
        reading order of the previous layout seeds the automatic layout.
        Assignments whose photo is missing or has invalid dimensions are
        skipped; they will be reported as displaced.
        """
        assignments = AssignmentRepository(connection).list_by_page(page.id)
        old_layout = (
            LayoutRepository(connection).get_by_id(page.layout_id)
            if page.layout_id is not None
            else None
        )
        positions = {slot.id: slot.position for slot in old_layout.slots} if old_layout else {}
        assignments.sort(key=lambda item: (positions.get(item.slot_id, item.slot_id), item.id))

        photos = PhotoRepository(connection).get_many([item.photo_id for item in assignments])
        pairs: list[tuple[PhotoAssignment, PhotoAsset]] = []
        for assignment in assignments:
            photo = photos.get(assignment.photo_id)
            if photo is None or photo.width <= 0 or photo.height <= 0:
                continue
            pairs.append((assignment, photo))
        return pairs

    def _plan_auto_change(self, project_id: int, page_id: int) -> LayoutChangePreview:
        """Preview an automatic layout change without persisting a snapshot."""
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            pairs, slots = self._auto_layout_for_page(connection, project_id, page)
            pair_ids = {assignment.id for assignment, _ in pairs}
            displaced = [
                item
                for item in AssignmentRepository(connection).list_by_page(page_id)
                if item.id not in pair_ids
            ]
            photos = PhotoRepository(connection)
            displaced_photos = tuple(
                photo
                for photo in (photos.get(item.photo_id) for item in displaced)
                if photo is not None
            )
            preserved = tuple((photo.id, f"auto_{index}") for index, (_, photo) in enumerate(pairs))
            return LayoutChangePreview(
                page_id=page_id,
                layout_key=AUTO_LAYOUT_KEY,
                layout_name=AUTO_LAYOUT_NAME,
                slot_count=len(slots),
                preserved=preserved,
                displaced=displaced_photos,
            )

    @staticmethod
    def _is_auto_layout(layout) -> bool:
        """Return whether a persisted layout is an automatic snapshot."""
        return layout is not None and layout.key == AUTO_LAYOUT_KEY

    def _importance_for_photos(
        self,
        connection,
        project_id: int,
        photos: list[PhotoAsset],
    ) -> list[float]:
        """Return per-photo importance using the project's score factor."""
        if self._object_detector is None or not photos:
            return [1.0] * len(photos)
        project = ProjectRepository(connection).get(project_id)
        if project is None:
            raise ProjectError(f"project {project_id} does not exist")
        factor = profile_from_project(project).layout.image_score_factor
        if factor <= 0.0:
            return [1.0] * len(photos)
        scorer = self._importance_scorers.get(factor)
        if scorer is None:
            scorer = ImportanceScorer(self._object_detector, factor)
            self._importance_scorers[factor] = scorer
        return scorer.score_photos(connection, photos)

    def _auto_layout_for_page(
        self, connection, project_id: int, page
    ) -> tuple[list[tuple[PhotoAssignment, PhotoAsset]], tuple[AutoSlot, ...]]:
        """Build automatic slots for a page using the photos already assigned to it.

        This is the composition helper used by add/reflow: it reads the current
        assignments (including empty holes) and orders them by their slot
        position, so the resulting ``pairs[i]`` is the assignment that should
        occupy ``auto_<i>``.
        """
        pairs = self._auto_pairs(connection, page)
        aspect = self._collage_aspect(connection, project_id, page)

        importance = self._importance_for_photos(
            connection, project_id, [photo for _, photo in pairs]
        )
        ordered_pairs, ordered_photos = _order_pairs_by_engine(pairs, importance)
        slots = build_auto_layout(ordered_photos, aspect)
        return ordered_pairs, slots

    def _change_layout_auto(self, project_id: int, page_id: int) -> LayoutChangePreview:
        """Apply an automatic layout change with a fresh persisted snapshot."""
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            pairs, slots = self._auto_layout_for_page(connection, project_id, page)
            return self._persist_auto_snapshot(connection, project_id, page, pairs, slots)

    def _persist_auto_snapshot(
        self,
        connection,
        project_id: int,
        page,
        pairs: list[tuple[PhotoAssignment, PhotoAsset]],
        slots: tuple[AutoSlot, ...],
    ) -> LayoutChangePreview:
        """Persist a new auto snapshot and remap assignments by slot index."""
        page_repository = PageRepository(connection)
        layout_repository = LayoutRepository(connection)
        version = layout_repository.next_version(AUTO_LAYOUT_KEY)
        slot_rows = [
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
                crop_mode="cover",
            )
            for index, slot in enumerate(slots)
        ]
        layout = layout_repository.add(AUTO_LAYOUT_KEY, version, AUTO_LAYOUT_NAME, slot_rows)

        assignments = AssignmentRepository(connection)
        existing = assignments.list_by_page(page.id)
        pair_ids = {assignment.id for assignment, _ in pairs}
        displaced = [item for item in existing if item.id not in pair_ids]
        for assignment in existing:
            assignments.remove(assignment.id)
        # Point the page at the new snapshot before inserting assignments so
        # the repository validates the new slot ids against the new layout.
        page_repository.set_layout(page.id, layout.id, layout.version)
        hole_slots: set[int] = set()
        for index, (assignment, _photo) in enumerate(pairs):
            target = layout.slots[index]
            if assignment.photo_id == 0:
                # A synthetic placeholder keeps the cell but leaves it empty.
                hole_slots.add(target.id)
                continue
            assignments.assign(
                project_id=project_id,
                page_id=page.id,
                slot_id=target.id,
                photo_id=assignment.photo_id,
                crop_zoom=assignment.crop_zoom,
                crop_focus_x=assignment.crop_focus_x,
                crop_focus_y=assignment.crop_focus_y,
            )

        photos = PhotoRepository(connection)
        displaced_photos = tuple(
            photo
            for photo in (photos.get(item.photo_id) for item in displaced)
            if photo is not None
        )
        preserved = tuple(
            (photo.id, layout.slots[index].slot_key)
            for index, (_, photo) in enumerate(pairs)
            if photo.id != 0
        )
        return LayoutChangePreview(
            page_id=page.id,
            layout_key=AUTO_LAYOUT_KEY,
            layout_name=AUTO_LAYOUT_NAME,
            slot_count=len(layout.slots) - len(hole_slots),
            preserved=preserved,
            displaced=displaced_photos,
        )

    def auto_add(self, project_id: int, page_id: int, photo_id: int) -> bool:
        """Add a photo to an automatic page.

        An empty slot is filled in place. When every slot is occupied the layout
        is regenerated for ``n + 1`` photos, which preserves every existing
        assignment, crop override and the reading order.

        Returns:
            ``True`` when the layout was regenerated, ``False`` when the photo
            filled an existing empty slot.

        Raises:
            ProjectError: If the page is not an auto layout, the photo is
                unavailable, or the request is invalid.
        """
        with self._database.transaction() as connection:
            page_repository = PageRepository(connection)
            page = page_repository.get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            layout = (
                LayoutRepository(connection).get_by_id(page.layout_id)
                if page.layout_id is not None
                else None
            )
            if not self._is_auto_layout(layout):
                raise ProjectError(f"page {page_id} does not use the automatic layout")

            photo = PhotoRepository(connection).get(photo_id)
            if photo is None or not photo.available:
                raise ProjectError(f"photo {photo_id} is not available")

            assignments = AssignmentRepository(connection)
            occupied = {assignment.slot_id for assignment in assignments.list_by_page(page_id)}
            empty_slot = next((slot for slot in layout.slots if slot.id not in occupied), None)
            if empty_slot is not None:
                assignments.assign(
                    project_id=project_id,
                    page_id=page_id,
                    slot_id=empty_slot.id,
                    photo_id=photo_id,
                )
                page_repository.increment_revision(page_id)
                return False

            pairs = self._auto_pairs(connection, page)
            # ``_auto_pairs`` skips unassigned slots, so holes created by a
            # removal are not represented. Re-insert one neutral placeholder
            # per hole at its original position to keep the grid unchanged.
            occupied = {assignment.slot_id for assignment in assignments.list_by_page(page_id)}
            if len(occupied) < len(layout.slots):
                pairs = self._pairs_with_holes(page, layout, pairs, occupied)
            pairs.append(
                (
                    PhotoAssignment(
                        id=0,
                        project_id=project_id,
                        page_id=page_id,
                        slot_id=0,
                        photo_id=photo_id,
                        crop_zoom=1.0,
                        crop_focus_x=0.5,
                        crop_focus_y=0.5,
                        created_at="",
                    ),
                    photo,
                )
            )
            importance = self._importance_for_photos(
                connection, project_id, [item for _, item in pairs]
            )
            ordered_pairs, ordered_photos = _order_pairs_by_engine(pairs, importance)
            slots = build_auto_layout(
                ordered_photos, self._collage_aspect(connection, project_id, page)
            )
            self._persist_auto_snapshot(connection, project_id, page, ordered_pairs, slots)
            return True

    def auto_add_many(
        self,
        project_id: int,
        page_id: int,
        photo_ids: list[int] | tuple[int, ...],
    ) -> tuple[int, bool]:
        """Add several photos to an automatic page in one transaction.

        Empty slots are filled first. Any remaining photos trigger one reflow
        that keeps existing crop overrides and hole placeholders. Unavailable
        or unknown photos are skipped.

        Returns:
            ``(added, regenerated)`` where ``added`` is the number of photos
            placed and ``regenerated`` indicates whether a new snapshot was
            written.

        Raises:
            ProjectError: If the page is not an automatic layout.
        """
        with self._database.transaction() as connection:
            page_repository = PageRepository(connection)
            page = page_repository.get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            layout = (
                LayoutRepository(connection).get_by_id(page.layout_id)
                if page.layout_id is not None
                else None
            )
            if not self._is_auto_layout(layout):
                raise ProjectError(f"page {page_id} does not use the automatic layout")
            return self._auto_add_many_in_transaction(
                connection, project_id, page, layout, photo_ids
            )

    def _auto_add_many_in_transaction(
        self,
        connection,
        project_id: int,
        page,
        layout,
        photo_ids: list[int] | tuple[int, ...],
    ) -> tuple[int, bool]:
        """Add photos using an already-open transaction and validated page."""
        photo_repository = PhotoRepository(connection)
        selected: list[tuple[int, PhotoAsset]] = []
        seen: set[int] = set()
        for photo_id in photo_ids:
            if photo_id in seen:
                continue
            photo = photo_repository.get(photo_id)
            if photo is None or not photo.available:
                continue
            seen.add(photo_id)
            selected.append((photo_id, photo))
        if not selected:
            return 0, False

        assignments = AssignmentRepository(connection)
        occupied = {assignment.slot_id for assignment in assignments.list_by_page(page.id)}
        empty_slots = [slot for slot in layout.slots if slot.id not in occupied]
        remaining: list[tuple[int, PhotoAsset]] = []
        added = 0
        for photo_id, photo in selected:
            if not empty_slots:
                remaining.append((photo_id, photo))
                continue
            slot = empty_slots.pop(0)
            assignments.assign(
                project_id=project_id,
                page_id=page.id,
                slot_id=slot.id,
                photo_id=photo_id,
            )
            added += 1

        if not remaining:
            PageRepository(connection).increment_revision(page.id)
            return added, False

        pairs = self._auto_pairs(connection, page)
        occupied = {assignment.slot_id for assignment in assignments.list_by_page(page.id)}
        if len(occupied) < len(layout.slots):
            pairs = self._pairs_with_holes(page, layout, pairs, occupied)
        for photo_id, photo in remaining:
            pairs.append(
                (
                    PhotoAssignment(
                        id=0,
                        project_id=project_id,
                        page_id=page.id,
                        slot_id=0,
                        photo_id=photo_id,
                        crop_zoom=1.0,
                        crop_focus_x=0.5,
                        crop_focus_y=0.5,
                        created_at="",
                    ),
                    photo,
                )
            )
        importance = self._importance_for_photos(
            connection, project_id, [photo for _, photo in pairs]
        )
        ordered_pairs, ordered_photos = _order_pairs_by_engine(pairs, importance)
        slots = build_auto_layout(
            ordered_photos, self._collage_aspect(connection, project_id, page)
        )
        self._persist_auto_snapshot(connection, project_id, page, ordered_pairs, slots)
        return added + len(remaining), True

    def auto_fill_unused(
        self,
        project_id: int,
        page_id: int,
        limit: int,
    ) -> tuple[int, bool]:
        """Fill up to ``limit`` unused available photos into an automatic page.

        Selects up to ``limit`` available photos that are not assigned anywhere
        in the project (inventory ``relative_path`` order, the same order as
        :meth:`populate`) and places them with the same logic as
        :meth:`auto_add_many`: empty slots are filled first and a single reflow
        happens when there are more photos than holes.

        Args:
            project_id: Project that owns the page.
            page_id: Page that uses the automatic layout.
            limit: Maximum number of photos to add (inclusive range 1-99).

        Returns:
            ``(added, regenerated)`` where ``added`` is the number of photos
            placed and ``regenerated`` indicates whether a new snapshot was
            written.

        Raises:
            ProjectError: If the page is not an automatic layout or ``limit``
                is outside the inclusive range 1-99.
        """
        if limit < 1 or limit > 99:
            raise ProjectError("limit must be between 1 and 99")
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            layout = (
                LayoutRepository(connection).get_by_id(page.layout_id)
                if page.layout_id is not None
                else None
            )
            if not self._is_auto_layout(layout):
                raise ProjectError(f"page {page_id} does not use the automatic layout")
            used_photo_ids = {
                assignment.photo_id
                for assignment in AssignmentRepository(connection).list_by_project(project_id)
            }
            candidates = [
                photo.id
                for photo in PhotoRepository(connection).list(project_id, available_only=True)
                if photo.id not in used_photo_ids
            ][:limit]
            if not candidates:
                return 0, False
            return self._auto_add_many_in_transaction(
                connection, project_id, page, layout, candidates
            )

    def uses_auto_layout(self, project_id: int, page_id: int) -> bool:
        """Return whether a page currently uses an automatic snapshot."""
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            layout = (
                LayoutRepository(connection).get_by_id(page.layout_id)
                if page.layout_id is not None
                else None
            )
            return self._is_auto_layout(layout)

    def auto_reflow(self, project_id: int, page_id: int) -> bool:
        """Regenerate an automatic layout with one slot per assigned photo.

        Empty holes left by removal are dropped and the remaining photos are
        re-tiled. Returns ``True`` when a new snapshot was written, ``False``
        when the page is not an automatic layout.
        """
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            layout = (
                LayoutRepository(connection).get_by_id(page.layout_id)
                if page.layout_id is not None
                else None
            )
            if not self._is_auto_layout(layout):
                return False
            pairs, slots = self._auto_layout_for_page(connection, project_id, page)
            self._persist_auto_snapshot(connection, project_id, page, pairs, slots)
            return True

    def auto_remove_empty(self, project_id: int, page_id: int) -> bool:
        """Drop empty slots from an automatic layout.

        This is the inverse of :meth:`auto_reflow` with respect to slot count:
        the remaining photos keep their assignments and the snapshot is rebuilt
        with exactly one slot per assigned photo. When no slot is empty the
        layout is left untouched.

        Returns:
            ``True`` when a new snapshot was written, ``False`` otherwise.
        """
        with self._database.transaction() as connection:
            page = PageRepository(connection).get(page_id)
            if page is None or page.project_id != project_id:
                raise ProjectError(f"page {page_id} does not exist")
            layout = (
                LayoutRepository(connection).get_by_id(page.layout_id)
                if page.layout_id is not None
                else None
            )
            if not self._is_auto_layout(layout):
                return False
            occupied = {
                assignment.slot_id
                for assignment in AssignmentRepository(connection).list_by_page(page_id)
            }
            if len(occupied) == len(layout.slots):
                return False
            pairs, slots = self._auto_layout_for_page(connection, project_id, page)
            self._persist_auto_snapshot(connection, project_id, page, pairs, slots)
            return True

    def regenerate_auto_layouts(
        self,
        project_id: int,
        *,
        object_detector: ObjectDetector | None = None,
    ) -> int:
        """Rebuild every automatic snapshot in a project.

        This is used after an output-profile change (page size, DPI, spacing,
        score factor) or a source rescan, both of which can change the canvas
        geometry or the importance of assigned photos. Empty automatic pages
        are skipped because they have no geometry to regenerate.

        Args:
            project_id: Project whose automatic pages are rebuilt.
            object_detector: Optional detector override. When supplied it
                replaces the detector configured on this service and clears
                cached scorers.

        Returns:
            The number of automatic snapshots that were regenerated.

        Raises:
            ProjectError: If the project does not exist.
        """
        if object_detector is not None:
            self._object_detector = object_detector
            self._importance_scorers.clear()

        regenerated = 0
        with self._database.transaction() as connection:
            if ProjectRepository(connection).get(project_id) is None:
                raise ProjectError(f"project {project_id} does not exist")
            assignments = AssignmentRepository(connection)
            for page in PageRepository(connection).list(project_id):
                if page.layout_id is None:
                    continue
                layout = LayoutRepository(connection).get_by_id(page.layout_id)
                if not self._is_auto_layout(layout):
                    continue
                pairs = self._auto_pairs(connection, page)
                occupied = {assignment.slot_id for assignment in assignments.list_by_page(page.id)}
                if not pairs and not occupied:
                    continue
                if len(occupied) < len(layout.slots):
                    pairs = self._pairs_with_holes(page, layout, pairs, occupied)
                importance = self._importance_for_photos(
                    connection, project_id, [photo for _, photo in pairs]
                )
                ordered_pairs, ordered_photos = _order_pairs_by_engine(pairs, importance)
                slots = build_auto_layout(
                    ordered_photos, self._collage_aspect(connection, project_id, page)
                )
                self._persist_auto_snapshot(connection, project_id, page, ordered_pairs, slots)
                regenerated += 1
        return regenerated

    def reset_all_layouts_to_auto(
        self,
        project_id: int,
        *,
        preserve_assignments: bool = True,
    ) -> int:
        """Switch every page of a project to the Automatic layout.

        In the default preserve mode the photos already assigned to each page
        are kept (with their crop overrides) and the automatic snapshot is
        rebuilt from them. Empty pages receive an empty automatic snapshot.
        When ``preserve_assignments`` is ``False`` the assignments are cleared
        first and every page receives an empty automatic snapshot; this is the
        mode used by distribution before applying a new proposal.

        Args:
            project_id: Project whose pages are reset.
            preserve_assignments: Keep the current photos and crop settings.

        Returns:
            The number of pages that were changed.

        Raises:
            ProjectError: If the project does not exist.
        """
        with self._database.transaction() as connection:
            if ProjectRepository(connection).get(project_id) is None:
                raise ProjectError(f"project {project_id} does not exist")
            changed = self._reset_layouts_in_transaction(
                connection,
                project_id,
                preserve_assignments=preserve_assignments,
            )
            if changed:
                PageRepository(connection).increment_revisions(project_id)
            return changed

    @staticmethod
    def _reset_layouts_in_transaction(
        connection,
        project_id: int,
        *,
        preserve_assignments: bool = True,
    ) -> int:
        """Reset every page to Automatic using an already-open transaction.

        This helper lets :meth:`DistributionService.apply` reuse the reset
        without nesting transaction blocks. The caller is responsible for
        incrementing page revisions and enqueuing previews when needed.

        Returns:
            The number of pages that were changed.
        """
        pages = PageRepository(connection).list(project_id)
        if not pages:
            return 0

        page_repo = PageRepository(connection)
        layout_repo = LayoutRepository(connection)
        assignment_repo = AssignmentRepository(connection)
        photos_repo = PhotoRepository(connection)
        project = ProjectRepository(connection).get(project_id)
        profile = profile_from_project(project) if project is not None else OutputProfile.default()

        changed = 0
        for page in pages:
            rows: list[tuple[int, float, float, float]] = []
            if preserve_assignments:
                for assignment in assignment_repo.list_by_page(page.id):
                    photo = photos_repo.get(assignment.photo_id)
                    if photo is None or photo.width <= 0 or photo.height <= 0:
                        continue
                    rows.append(
                        (
                            assignment.photo_id,
                            assignment.crop_zoom,
                            assignment.crop_focus_x,
                            assignment.crop_focus_y,
                        )
                    )

            for assignment in assignment_repo.list_by_page(page.id):
                assignment_repo.remove(assignment.id)

            if not rows:
                version = layout_repo.next_version(AUTO_LAYOUT_KEY)
                layout = layout_repo.add(AUTO_LAYOUT_KEY, version, AUTO_LAYOUT_NAME, [])
                page_repo.set_layout(page.id, layout.id, layout.version)
                changed += 1
                continue

            engine_photos = tuple(
                AutoPhoto(
                    key=str(photo_id),
                    width=photos_repo.get(photo_id).width,
                    height=photos_repo.get(photo_id).height,
                    importance=1.0,
                )
                for photo_id, _zoom, _fx, _fy in rows
            )
            aspect = collage_aspect_for_page(page, profile)
            slots = build_auto_layout(engine_photos, aspect)
            version = layout_repo.next_version(AUTO_LAYOUT_KEY)
            slot_rows = [
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
                    crop_mode="cover",
                )
                for index, slot in enumerate(slots)
            ]
            layout = layout_repo.add(AUTO_LAYOUT_KEY, version, AUTO_LAYOUT_NAME, slot_rows)
            page_repo.set_layout(page.id, layout.id, layout.version)
            for slot, (photo_id, zoom, fx, fy) in zip(layout.slots, rows, strict=False):
                assignment_repo.assign(
                    project_id=project_id,
                    page_id=page.id,
                    slot_id=slot.id,
                    photo_id=photo_id,
                    crop_zoom=zoom,
                    crop_focus_x=fx,
                    crop_focus_y=fy,
                )
            changed += 1
        return changed

    def _collage_aspect(self, connection, project_id: int, page) -> float:
        """Return the collage content-box aspect ratio for one page."""
        project = ProjectRepository(connection).get(project_id)
        if project is None:
            raise ProjectError(f"project {project_id} does not exist")
        profile = profile_from_project(project)
        return collage_aspect_for_page(page, profile)

    @staticmethod
    def _pairs_with_holes(
        page,
        layout,
        pairs: list[tuple[PhotoAssignment, PhotoAsset]],
        occupied: set[int],
    ) -> list[tuple[PhotoAssignment, PhotoAsset]]:
        """Re-insert neutral placeholders for slots left empty by a removal.

        A hole is represented by a synthetic assignment that carries no photo id
        and a square placeholder photo. :meth:`_persist_auto_snapshot` keeps its
        cell and leaves the slot empty, so the visible grid does not move when a
        photo is added to an auto page with holes.
        """
        positions = {slot.id: slot.position for slot in layout.slots}
        placeholders = [
            (
                PhotoAssignment(
                    id=0,
                    project_id=page.project_id,
                    page_id=page.id,
                    slot_id=slot.id,
                    photo_id=0,
                    crop_zoom=1.0,
                    crop_focus_x=0.5,
                    crop_focus_y=0.5,
                    created_at="",
                ),
                PhotoAsset(
                    id=0,
                    project_id=page.project_id,
                    source_root_id=0,
                    relative_path="",
                    filename="",
                    file_size=0,
                    mtime=None,
                    digest=None,
                    width=1,
                    height=1,
                    captured_at=None,
                    gps_lat=None,
                    gps_lon=None,
                    available=False,
                    created_at="",
                ),
            )
            for slot in layout.slots
            if slot.id not in occupied
        ]
        merged = sorted(
            [*pairs, *placeholders],
            key=lambda item: positions.get(item[0].slot_id, item[0].slot_id),
        )
        return merged

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
            return self._plan_auto_change(project_id, page_id)
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
            return self._change_layout_auto(project_id, page_id)
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
