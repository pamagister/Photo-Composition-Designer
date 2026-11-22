"""Pure distribution proposal service.

Produces :class:`DistributionProposal` objects from persisted photo inventory
and page metadata without mutating project state. Applying a proposal is a
separate transactional operation in :class:`DistributionService.apply`.

Modes:
- ``all``: consider every available photo and reset every page to Automatic.
- ``best``: rank all available photos, select the top K and reset every page to
  Automatic.
- ``slots``: keep the current page layouts and fill only the unassigned photos.

Strategies:
- ``equal``: photos are split as evenly as possible across pages.
- ``random``: equal split with a seeded, reproducible shuffle.
- ``date_grouped``: a dynamic-programming partition that keeps same-day and
  consecutive-day photos together (``all`` and ``best`` modes).
- ``date_aware``: photos are matched to the calendar week of each page's
  ``start_date``; unmatched photos overflow to the unused pool (``slots`` mode).
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.io.media import resolve_source_path
from photo_composition_designer.layouts.auto_layout import (
    AutoPhoto,
    build_auto_layout,
    order_photos,
)
from photo_composition_designer.layouts.loader import AUTO_LAYOUT_KEY, AUTO_LAYOUT_NAME
from photo_composition_designer.project.date_grouping import (
    GroupingWeights,
    partition_by_date,
)
from photo_composition_designer.project.importance import ImportanceScorer
from photo_composition_designer.project.models import (
    CalendarPage,
    DistributionProposal,
    LayoutSlot,
    PhotoAsset,
)
from photo_composition_designer.project.quality import QualityScorer, SelectionScorer
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
    SourceRootRepository,
)
from photo_composition_designer.render.object_detector import ObjectDetector

#: Aspect-ratio band treated as square for orientation matching.
_ORIENTATION_SQUARE_MIN = 0.9
_ORIENTATION_SQUARE_MAX = 1.1

#: Accepted distribution modes.
VALID_MODES = frozenset({"all", "best", "slots"})

#: Accepted distribution strategies.
VALID_STRATEGIES = frozenset({"equal", "random", "date_grouped", "date_aware"})

#: Target average number of photos per page for each best-range preset.
_BEST_RANGE_TARGETS: dict[str, int] = {
    "2-5": 4,
    "3-5": 4,
    "3-6": 5,
    "3-7": 5,
}

#: Bounds (min, max) photos per page for each best-range preset.
_BEST_RANGE_BOUNDS: dict[str, tuple[int, int]] = {
    "2-5": (2, 5),
    "3-5": (3, 5),
    "3-6": (3, 6),
    "3-7": (3, 7),
}


def _classify_aspect_ratio(ratio: float) -> str:
    """Classify an aspect ratio (width / height) as portrait, landscape or square."""
    if ratio < _ORIENTATION_SQUARE_MIN:
        return "portrait"
    if ratio > _ORIENTATION_SQUARE_MAX:
        return "landscape"
    return "square"


def _slot_orientation(slot: LayoutSlot, page_aspect: float) -> str:
    """Return a slot's rendered orientation given the page aspect ratio.

    Slot coordinates are normalized, so the page aspect ratio is applied to
    recover the real on-page width/height ratio before classifying.
    """
    if slot.height <= 0:
        return "square"
    return _classify_aspect_ratio((slot.width / slot.height) * page_aspect)


def _photo_orientation(photo: PhotoAsset) -> str:
    """Return a photo's orientation from its pixel dimensions."""
    if photo.height <= 0:
        return "square"
    return _classify_aspect_ratio(photo.width / photo.height)


@dataclass(frozen=True)
class ProposalSummary:
    """Human-readable counts for a proposal preview."""

    pages: int
    total_photos: int
    assigned: int
    unassigned: int
    empty_slots_per_page: list[int]
    overflow: int
    not_selected: int = 0
    target: float | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable summary."""
        return {
            "pages": self.pages,
            "total_photos": self.total_photos,
            "assigned": self.assigned,
            "unassigned": self.unassigned,
            "empty_slots_per_page": self.empty_slots_per_page,
            "overflow": self.overflow,
            "not_selected": self.not_selected,
            "target": self.target,
        }


class DistributionService:
    """Build and apply distribution proposals for a project."""

    def __init__(self, database: WorkspaceDatabase) -> None:
        self._database = database

    def _load_pages(self, connection, project_id: int) -> list[CalendarPage]:
        return PageRepository(connection).list(project_id)

    def _page_layout_key(self, connection, page: CalendarPage) -> str | None:
        """Return the layout key of a page, or ``None`` when it has no layout."""
        if page.layout_id is None:
            return None
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        return layout.key if layout is not None else None

    def _page_slot_capacity(
        self,
        connection,
        page: CalendarPage,
        fallback: int,
    ) -> int:
        """Return the number of slots available on a page's layout.

        Static pages keep their slot count. Automatic pages have no fixed slot
        count, so the supplied computed fallback is used as their capacity.
        """
        if page.layout_id is None:
            return 0
        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        if layout is None:
            return 0
        if layout.key == AUTO_LAYOUT_KEY:
            return max(1, fallback)
        return len(layout.slots)

    def capacity_for_page(self, connection, project_id: int, page: CalendarPage) -> int:
        """Return the capacity used by distribution previews for one page."""
        return self._page_slot_capacity(
            connection, page, self._fallback_target(connection, project_id)
        )

    def _fallback_target(self, connection, project_id: int) -> int:
        """Return the computed automatic-page target for the current project."""
        pages = self._load_pages(connection, project_id)
        if not pages:
            return 1
        photos = PhotoRepository(connection).list(project_id, available_only=True)
        return max(1, round(len(photos) / len(pages)))

    def _available_photos(self, connection, project_id: int) -> list[int]:
        """Return every available photo id in inventory order."""
        return [
            photo.id for photo in PhotoRepository(connection).list(project_id, available_only=True)
        ]

    def _unassigned_photo_ids(self, connection, project_id: int) -> list[int]:
        """Return available photo ids that are not assigned anywhere."""
        assigned = {a.photo_id for a in AssignmentRepository(connection).list(project_id)}
        return [
            photo_id
            for photo_id in self._available_photos(connection, project_id)
            if photo_id not in assigned
        ]

    def _photo_capture_dates(
        self,
        connection,
        photo_ids: list[int],
    ) -> dict[int, datetime | None]:
        """Return the capture date for each photo id."""
        photo_repo = PhotoRepository(connection)
        captured: dict[int, datetime | None] = {}
        for photo_id in photo_ids:
            photo = photo_repo.get(photo_id)
            value = None
            if photo is not None and photo.captured_at is not None:
                try:
                    value = datetime.fromisoformat(photo.captured_at)
                except ValueError:
                    value = None
            captured[photo_id] = value
        return captured

    def _photo_paths(self, connection, photo_ids: list[int]) -> dict[int, Path]:
        """Resolve the on-disk path for each photo id that can be read."""
        photo_repo = PhotoRepository(connection)
        roots = SourceRootRepository(connection).get_many(
            [
                photo.source_root_id
                for photo in (photo_repo.get(photo_id) for photo_id in photo_ids)
                if photo is not None
            ]
        )
        paths: dict[int, Path] = {}
        for photo_id in photo_ids:
            photo = photo_repo.get(photo_id)
            if photo is None:
                continue
            root = roots.get(photo.source_root_id)
            if root is None:
                continue
            try:
                path = resolve_source_path(root.path, photo.relative_path)
            except ValueError:
                continue
            if path.is_file():
                paths[photo_id] = path
        return paths

    def propose(
        self,
        project_id: int,
        *,
        mode: str = "slots",
        strategy: str = "equal",
        seed: int | None = None,
        best_range: str = "3-5",
        object_detector: ObjectDetector | None = None,
    ) -> DistributionProposal:
        """Build a distribution proposal without mutating project state."""
        if mode not in VALID_MODES:
            raise ValueError(f"unknown distribution mode: {mode}")
        if strategy not in VALID_STRATEGIES:
            raise ValueError(f"unknown distribution strategy: {strategy}")

        with self._database.transaction() as connection:
            pages = self._load_pages(connection, project_id)
            if not pages:
                return DistributionProposal(
                    strategy=strategy,
                    pages=[],
                    unassigned=[],
                    mode=mode,
                )

            project = ProjectRepository(connection).get(project_id)
            profile = (
                profile_from_project(project) if project is not None else OutputProfile.default()
            )
            if mode == "slots":
                return self._propose_slots(
                    connection,
                    project_id,
                    pages,
                    profile,
                    strategy,
                    seed,
                )

            return self._propose_all_or_best(
                connection,
                project_id,
                pages,
                profile,
                mode=mode,
                strategy=strategy,
                seed=seed,
                best_range=best_range,
                object_detector=object_detector,
            )

    def _propose_slots(
        self,
        connection,
        project_id: int,
        pages: list[CalendarPage],
        profile: OutputProfile,
        strategy: str,
        seed: int | None,
    ) -> DistributionProposal:
        """Build a proposal for the current layouts using unassigned photos."""
        fallback = self._fallback_target(connection, project_id)
        capacities = [self._page_slot_capacity(connection, page, fallback) for page in pages]
        total_capacity = sum(capacities)
        photos = self._unassigned_photo_ids(connection, project_id)

        if strategy == "random":
            effective_seed = seed if seed is not None else 11
            rng = random.Random(effective_seed)
            rng.shuffle(photos)
            grouped = self._split_equally(photos, capacities, total_capacity)
            return DistributionProposal(
                strategy=strategy,
                pages=grouped,
                unassigned=[],
                seed=effective_seed,
                mode="slots",
                target=float(fallback),
            )

        if strategy == "date_aware":
            grouped, overflow = self._split_by_date(pages, photos, connection)
            return DistributionProposal(
                strategy=strategy,
                pages=grouped,
                unassigned=overflow,
                seed=None,
                mode="slots",
                target=float(fallback),
            )

        if strategy == "date_grouped":
            raise ValueError("date_grouped is only available in 'all' and 'best' modes")

        grouped, overflow = self._split_equally_with_overflow(photos, capacities)
        return DistributionProposal(
            strategy=strategy,
            pages=grouped,
            unassigned=overflow,
            seed=None,
            mode="slots",
            target=float(fallback),
        )

    def _propose_all_or_best(
        self,
        connection,
        project_id: int,
        pages: list[CalendarPage],
        profile: OutputProfile,
        *,
        mode: str,
        strategy: str,
        seed: int | None,
        best_range: str,
        object_detector: ObjectDetector | None,
    ) -> DistributionProposal:
        """Build a proposal that considers all photos and resets to Automatic."""
        if strategy == "date_aware":
            raise ValueError("date_aware is only available in 'slots' mode")

        page_count = len(pages)
        available = self._available_photos(connection, project_id)
        selected = available
        not_selected: list[int] = []
        bounds: tuple[int, int] | None = None

        if mode == "best":
            if best_range not in _BEST_RANGE_TARGETS:
                raise ValueError(f"unknown best range preset: {best_range}")
            target_average = _BEST_RANGE_TARGETS[best_range]
            bounds = _BEST_RANGE_BOUNDS[best_range]
            keep = min(len(available), round(page_count * target_average))
            selected, not_selected = self._select_best(
                connection,
                available,
                keep,
                profile,
                object_detector,
            )

        if not selected:
            return DistributionProposal(
                strategy=strategy,
                pages=[[] for _ in pages],
                unassigned=[],
                mode=mode,
                reset_layouts=True,
                not_selected=not_selected,
                target=0.0,
            )

        target = len(selected) / page_count if page_count else 0.0

        if strategy == "random":
            effective_seed = seed if seed is not None else 11
            rng = random.Random(effective_seed)
            shuffled = list(selected)
            rng.shuffle(shuffled)
            grouped = self._split_contiguous(shuffled, page_count)
            return DistributionProposal(
                strategy=strategy,
                pages=grouped,
                unassigned=[],
                seed=effective_seed,
                mode=mode,
                reset_layouts=True,
                not_selected=not_selected,
                target=target,
            )

        captured = self._photo_capture_dates(connection, selected)
        if strategy == "date_grouped":
            dated = [(photo_id, captured[photo_id]) for photo_id in selected]
            weights = GroupingWeights()
            minimum = bounds[0] if bounds is not None else None
            maximum = bounds[1] if bounds is not None else None
            grouped = partition_by_date(
                dated,
                page_count,
                minimum=minimum,
                maximum=maximum,
                weights=weights,
            )
            return DistributionProposal(
                strategy=strategy,
                pages=grouped,
                unassigned=[],
                seed=None,
                mode=mode,
                reset_layouts=True,
                not_selected=not_selected,
                target=target,
            )

        # ``equal``: order by capture date, then split into contiguous groups.
        ordered = sorted(
            selected,
            key=lambda photo_id: (
                captured[photo_id] or datetime.max,
                self._photo_sort_name(connection, photo_id),
                photo_id,
            ),
        )
        grouped = self._split_contiguous(ordered, page_count)
        return DistributionProposal(
            strategy=strategy,
            pages=grouped,
            unassigned=[],
            seed=None,
            mode=mode,
            reset_layouts=True,
            not_selected=not_selected,
            target=target,
        )

    def _select_best(
        self,
        connection,
        available: list[int],
        keep: int,
        profile: OutputProfile,
        object_detector: ObjectDetector | None,
    ) -> tuple[list[int], list[int]]:
        """Rank available photos and return the selected and unselected ids."""
        if keep <= 0:
            return [], list(available)
        photos_by_id = {
            photo.id: photo
            for photo in PhotoRepository(connection).list(
                self._project_id_for(connection, available)
            )
        }
        return self._rank_and_select(
            connection,
            available,
            keep,
            profile,
            object_detector,
            photos_by_id,
        )

    @staticmethod
    def _project_id_for(connection, available: list[int]) -> int:
        """Return the project id for the available photo ids."""
        if not available:
            return 0
        row = connection.execute(
            "SELECT project_id FROM photos WHERE id = ? LIMIT 1",
            (available[0],),
        ).fetchone()
        return int(row["project_id"]) if row is not None else 0

    def _rank_and_select(
        self,
        connection,
        available: list[int],
        keep: int,
        profile: OutputProfile,
        object_detector: ObjectDetector | None,
        photos_by_id: dict[int, PhotoAsset],
    ) -> tuple[list[int], list[int]]:
        """Rank photos by selection score and split them into kept and rest."""
        paths = self._photo_paths(connection, available)
        quality = QualityScorer().score_all(paths)
        scorer = ImportanceScorer(object_detector, profile.layout.image_score_factor)
        selection = SelectionScorer(quality)

        captured = self._photo_capture_dates(connection, available)
        ranked = sorted(
            available,
            key=lambda photo_id: (
                -selection.score(
                    photo_id, scorer.importance_for(photos_by_id[photo_id], paths.get(photo_id))
                ),
                captured[photo_id] or datetime.max,
                photo_id,
            ),
        )
        selected = ranked[:keep]
        return selected, ranked[keep:]

    def _photo_sort_name(self, connection, photo_id: int) -> str:
        """Return the inventory filename used as a deterministic tie-breaker."""
        photo = PhotoRepository(connection).get(photo_id)
        return photo.filename if photo is not None else ""

    @staticmethod
    def _split_contiguous(photos: list[int], page_count: int) -> list[list[int]]:
        """Split a list into ``page_count`` contiguous, balanced groups."""
        if page_count <= 0:
            return []
        base, remainder = divmod(len(photos), page_count)
        grouped: list[list[int]] = []
        index = 0
        for page_index in range(page_count):
            size = base + (1 if page_index < remainder else 0)
            grouped.append(photos[index : index + size])
            index += size
        return grouped

    def _split_equally(
        self,
        photos: list[int],
        capacities: list[int],
        total_capacity: int,
    ) -> list[list[int]]:
        grouped: list[list[int]] = []
        index = 0
        for capacity in capacities:
            take = min(capacity, len(photos) - index)
            grouped.append(photos[index : index + take])
            index += take
        return grouped

    def _split_equally_with_overflow(
        self,
        photos: list[int],
        capacities: list[int],
    ) -> tuple[list[list[int]], list[int]]:
        grouped: list[list[int]] = []
        index = 0
        for capacity in capacities:
            take = min(capacity, len(photos) - index)
            grouped.append(photos[index : index + take])
            index += take
        overflow = photos[index:]
        return grouped, overflow

    def _split_by_date(
        self,
        pages: list[CalendarPage],
        photos: list[int],
        connection,
    ) -> tuple[list[list[int]], list[int]]:
        dated: list[tuple[int, datetime | None]] = [
            (photo_id, captured)
            for photo_id, captured in self._photo_capture_dates(connection, photos).items()
        ]

        grouped: list[list[int]] = []
        used: set[int] = set()
        for page in pages:
            week_start = datetime.fromisoformat(page.start_date)
            week_end = datetime.fromisoformat(page.end_date)
            in_week = [
                photo_id
                for photo_id, captured in dated
                if photo_id not in used
                and captured is not None
                and week_start.date() <= captured.date() <= week_end.date()
            ]
            grouped.append(in_week)
            used.update(in_week)

        overflow = [photo_id for photo_id, _ in dated if photo_id not in used]
        return grouped, overflow

    def summarize(
        self,
        proposal: DistributionProposal,
        *,
        capacities: list[int] | None = None,
    ) -> ProposalSummary:
        """Return counts for a proposal preview.

        When page slot capacities are supplied, the summary also reports how
        many slots remain empty per page.
        """
        total = sum(len(group) for group in proposal.pages)
        empty_slots = (
            [
                max(0, capacity - len(group))
                for capacity, group in zip(capacities, proposal.pages, strict=False)
            ]
            if capacities is not None
            else []
        )
        return ProposalSummary(
            pages=len(proposal.pages),
            total_photos=total,
            assigned=total,
            unassigned=len(proposal.unassigned),
            empty_slots_per_page=empty_slots,
            overflow=len(proposal.unassigned),
            not_selected=len(proposal.not_selected),
            target=proposal.target,
        )

    def digest(self, proposal: DistributionProposal) -> str:
        """Return a stable fingerprint for a previewed proposal.

        The fingerprint lets the confirm endpoint reject stale previews and
        makes repeated confirmation a no-op instead of a state change.
        """
        payload = {
            "mode": proposal.mode,
            "strategy": proposal.strategy,
            "seed": proposal.seed,
            "pages": proposal.pages,
            "unassigned": proposal.unassigned,
            "not_selected": proposal.not_selected,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _page_aspect(self, project) -> float:
        """Return the page width/height ratio used to classify slot orientation."""
        profile = (
            OutputProfile.from_dict(project.output_profile)
            if project is not None and project.output_profile
            else OutputProfile.default()
        )
        if profile.size.height <= 0:
            return 1.0
        return profile.size.width / profile.size.height

    def _match_photos_to_slots(
        self,
        slots: list[LayoutSlot],
        photo_ids: list[int],
        photos_by_id: dict[int, PhotoAsset],
        page_aspect: float,
    ) -> list[int]:
        """Reorder photo ids so portrait/landscape photos prefer matching slots.

        The proposal order is preserved as far as possible: for each slot in
        order, the first remaining photo with a matching orientation is used.
        When no orientation match remains, the next photo in proposal order is
        used so no photo is ever dropped.
        """
        remaining: list[tuple[int, str]] = []
        for photo_id in photo_ids:
            photo = photos_by_id.get(photo_id)
            orientation = _photo_orientation(photo) if photo is not None else "unknown"
            remaining.append((photo_id, orientation))

        ordered: list[int] = []
        for slot in slots:
            if not remaining:
                break
            slot_orientation = _slot_orientation(slot, page_aspect)
            match_index = next(
                (
                    index
                    for index, (_photo_id, orientation) in enumerate(remaining)
                    if orientation == slot_orientation
                ),
                None,
            )
            if match_index is None:
                match_index = 0
            photo_id, _orientation = remaining.pop(match_index)
            ordered.append(photo_id)
        return ordered

    def apply(
        self,
        project_id: int,
        proposal: DistributionProposal,
        *,
        object_detector: ObjectDetector | None = None,
    ) -> None:
        """Atomically replace assignments for a project with this proposal.

        Photos are matched to slots by orientation (portrait to portrait, etc.)
        where possible before the assignments are persisted. Automatic pages
        are regenerated from the photos they receive, so their geometry always
        matches the actual set and orientation mix.

        When ``proposal.reset_layouts`` is set (all and best modes), every page
        is first reset to an empty Automatic snapshot so the proposal is applied
        to automatic layouts.

        Args:
            project_id: Project whose assignments are replaced.
            proposal: Proposal produced by :meth:`propose`.
            object_detector: Optional detector used for content importance
                weighting on automatic pages.
        """
        from photo_composition_designer.project.editing import PageEditingService

        with self._database.transaction() as connection:
            if proposal.reset_layouts:
                PageEditingService._reset_layouts_in_transaction(
                    connection,
                    project_id,
                    preserve_assignments=False,
                )
            pages = {page.id: page for page in self._load_pages(connection, project_id)}
            if len(pages) != len(proposal.pages):
                raise ValueError("proposal page count does not match project pages")

            assignment_repo = AssignmentRepository(connection)
            layout_repo = LayoutRepository(connection)
            page_repo = PageRepository(connection)
            project = ProjectRepository(connection).get(project_id)
            profile = (
                profile_from_project(project) if project is not None else OutputProfile.default()
            )
            page_aspect = self._page_aspect(project)
            photos_by_id = {
                photo.id: photo for photo in PhotoRepository(connection).list(project_id)
            }
            assignment_repo.clear_for_project(project_id)

            ordered_pages = sorted(pages.values(), key=lambda page: page.page_index)
            for page, photo_ids in zip(ordered_pages, proposal.pages, strict=True):
                if page.layout_id is None:
                    continue
                layout = layout_repo.get_by_id(page.layout_id)
                if layout is None:
                    continue
                if layout.key == AUTO_LAYOUT_KEY:
                    self._apply_auto_page(
                        connection,
                        project_id,
                        page,
                        photo_ids,
                        photos_by_id,
                        profile,
                        assignment_repo,
                        layout_repo,
                        page_repo,
                        object_detector,
                    )
                    continue
                ordered_ids = self._match_photos_to_slots(
                    layout.slots, photo_ids, photos_by_id, page_aspect
                )
                for slot, photo_id in zip(layout.slots, ordered_ids, strict=False):
                    assignment_repo.assign(
                        project_id=project_id,
                        page_id=page.id,
                        slot_id=slot.id,
                        photo_id=photo_id,
                    )
            page_repo.increment_revisions(project_id)

    def _apply_auto_page(
        self,
        connection,
        project_id: int,
        page: CalendarPage,
        photo_ids: list[int],
        photos_by_id: dict[int, PhotoAsset],
        profile: OutputProfile,
        assignment_repo: AssignmentRepository,
        layout_repo: LayoutRepository,
        page_repo: PageRepository,
        object_detector: ObjectDetector | None,
    ) -> None:
        """Regenerate one automatic page from the photos it receives."""
        photos = [photos_by_id[photo_id] for photo_id in photo_ids if photo_id in photos_by_id]
        if not photos:
            # No photos to arrange. Leave the existing snapshot untouched so
            # the page keeps its empty state and slot count.
            return

        scorer = ImportanceScorer(
            object_detector,
            profile.layout.image_score_factor,
        )
        importance = scorer.score_photos(connection, photos)
        engine_photos = tuple(
            AutoPhoto(
                key=str(index),
                width=photo.width,
                height=photo.height,
                importance=score,
            )
            for index, (photo, score) in enumerate(zip(photos, importance, strict=True))
        )
        ordered_photos = [photos[int(photo.key)] for photo in order_photos(engine_photos)]
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
        for slot, photo in zip(layout.slots, ordered_photos, strict=False):
            assignment_repo.assign(
                project_id=project_id,
                page_id=page.id,
                slot_id=slot.id,
                photo_id=photo.id,
            )
