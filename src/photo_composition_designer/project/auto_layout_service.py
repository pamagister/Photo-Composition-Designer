"""Automatic page-layout generation, distribution and reflow operations."""

from __future__ import annotations

from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.layouts.auto_layout import AutoPhoto, AutoSlot, build_auto_layout
from photo_composition_designer.layouts.loader import AUTO_LAYOUT_KEY, AUTO_LAYOUT_NAME
from photo_composition_designer.project.importance import ImportanceScorer
from photo_composition_designer.project.layout_models import LayoutChangePreview
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


class AutomaticLayoutService:
    """Build and persist automatic layouts while preserving page assignments."""

    def __init__(
        self,
        database: WorkspaceDatabase,
        object_detector: ObjectDetector | None = None,
    ) -> None:
        self._database = database
        self._object_detector = object_detector
        self._importance_scorers: dict[float, ImportanceScorer] = {}

    def preview_layout_change(self, project_id: int, page_id: int) -> LayoutChangePreview:
        """Preview switching a page to an automatic layout."""
        return self._plan_auto_change(project_id, page_id)

    def change_to_automatic_layout(self, project_id: int, page_id: int) -> LayoutChangePreview:
        """Switch a page to a newly generated automatic layout."""
        return self._change_layout_auto(project_id, page_id)

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
