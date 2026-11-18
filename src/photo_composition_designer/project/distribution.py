"""Pure distribution proposal service.

Produces :class:`DistributionProposal` objects from persisted photo inventory
and page metadata without mutating project state. Applying a proposal is a
separate transactional operation in :class:`DistributionService.apply`.

Strategies:
- ``equal``: photos are split as evenly as possible across pages.
- ``random``: equal split with a seeded, reproducible shuffle.
- ``date_aware``: photos are matched to the calendar week of each page's
  ``start_date``; unmatched photos overflow to the unused pool.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime

from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.models import CalendarPage, DistributionProposal
from photo_composition_designer.project.repositories import (
    AssignmentRepository,
    PageRepository,
    PhotoRepository,
)


@dataclass(frozen=True)
class ProposalSummary:
    """Human-readable counts for a proposal preview."""

    pages: int
    total_photos: int
    assigned: int
    unassigned: int
    empty_slots_per_page: list[int]
    overflow: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable summary."""
        return {
            "pages": self.pages,
            "total_photos": self.total_photos,
            "assigned": self.assigned,
            "unassigned": self.unassigned,
            "empty_slots_per_page": self.empty_slots_per_page,
            "overflow": self.overflow,
        }


class DistributionService:
    """Build and apply distribution proposals for a project."""

    def __init__(self, database: WorkspaceDatabase) -> None:
        self._database = database

    def _load_pages(self, connection, project_id: int) -> list[CalendarPage]:
        return PageRepository(connection).list(project_id)

    def _page_slot_capacity(self, connection, page: CalendarPage) -> int:
        """Return the number of slots available on a page's layout."""
        if page.layout_id is None:
            return 0
        from photo_composition_designer.project.repositories import LayoutRepository

        layout = LayoutRepository(connection).get_by_id(page.layout_id)
        return len(layout.slots) if layout else 0

    def _unassigned_photo_ids(self, connection, project_id: int) -> list[int]:
        assigned = {a.photo_id for a in AssignmentRepository(connection).list(project_id)}
        return [
            photo.id
            for photo in PhotoRepository(connection).list(project_id, available_only=True)
            if photo.id not in assigned
        ]

    def propose(
        self,
        project_id: int,
        *,
        strategy: str = "equal",
        seed: int | None = None,
    ) -> DistributionProposal:
        """Build a distribution proposal without mutating project state."""
        with self._database.transaction() as connection:
            pages = self._load_pages(connection, project_id)
            if not pages:
                return DistributionProposal(strategy=strategy, pages=[], unassigned=[])

            capacities = [self._page_slot_capacity(connection, page) for page in pages]
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
                )

            if strategy == "date_aware":
                grouped, overflow = self._split_by_date(pages, photos, connection)
                return DistributionProposal(
                    strategy=strategy,
                    pages=grouped,
                    unassigned=overflow,
                    seed=None,
                )

            grouped, overflow = self._split_equally_with_overflow(photos, capacities)
            return DistributionProposal(
                strategy=strategy,
                pages=grouped,
                unassigned=overflow,
                seed=None,
            )

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
        photo_repo = PhotoRepository(connection)
        dated: list[tuple[int, datetime | None]] = []
        for photo_id in photos:
            photo = photo_repo.get(photo_id)
            captured = None
            if photo is not None and photo.captured_at is not None:
                try:
                    captured = datetime.fromisoformat(photo.captured_at)
                except ValueError:
                    captured = None
            dated.append((photo_id, captured))

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
        )

    def digest(self, proposal: DistributionProposal) -> str:
        """Return a stable fingerprint for a previewed proposal.

        The fingerprint lets the confirm endpoint reject stale previews and
        makes repeated confirmation a no-op instead of a state change.
        """
        payload = {
            "strategy": proposal.strategy,
            "seed": proposal.seed,
            "pages": proposal.pages,
            "unassigned": proposal.unassigned,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]

    def apply(self, project_id: int, proposal: DistributionProposal) -> None:
        """Atomically replace assignments for a project with this proposal."""
        with self._database.transaction() as connection:
            pages = {page.id: page for page in self._load_pages(connection, project_id)}
            if len(pages) != len(proposal.pages):
                raise ValueError("proposal page count does not match project pages")

            assignment_repo = AssignmentRepository(connection)
            from photo_composition_designer.project.repositories import LayoutRepository

            layout_repo = LayoutRepository(connection)
            assignment_repo.clear_for_project(project_id)

            ordered_pages = sorted(pages.values(), key=lambda page: page.page_index)
            for page, photo_ids in zip(ordered_pages, proposal.pages, strict=True):
                if page.layout_id is None:
                    continue
                layout = layout_repo.get_by_id(page.layout_id)
                if layout is None:
                    continue
                for slot, photo_id in zip(layout.slots, photo_ids, strict=False):
                    assignment_repo.assign(
                        project_id=project_id,
                        page_id=page.id,
                        slot_id=slot.id,
                        photo_id=photo_id,
                    )
            PageRepository(connection).increment_revisions(project_id)
