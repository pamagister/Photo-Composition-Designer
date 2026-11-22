"""Pure date-aware photo grouping used by the ``all`` and ``best`` modes.

The module contains no I/O. It partitions an ordered list of dated photos into a
fixed number of contiguous pages so that:

- page sizes stay close to a moving target (``remaining / remaining``),
- same-day and consecutive-day photos are kept together where possible,
- splitting one day across two pages and bridging large date gaps is penalised.

A banded dynamic program explores candidate page sizes around the moving target.
When the input is very large the band is widened by a coarse step to keep the
search tractable while still preferring balanced partitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

#: Upper bound on photos before the coarse DP band is used.
_LARGE_INPUT_THRESHOLD = 2000

#: Band width used for very large inputs.
_LARGE_BAND = 64


@dataclass(frozen=True)
class GroupingWeights:
    """Penalty weights for the date-grouping dynamic program."""

    deviation_weight: float = 1.0
    gap_weight: float = 1.0
    split_weight: float = 6.0
    below_min_weight: float = 2.0
    above_max_weight: float = 2.0


def _as_date(value: datetime | date | None) -> date | None:
    """Return the calendar date of a datetime, date or ``None``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _build_sort_key(
    photos: list[tuple[int, datetime | None]],
) -> list[tuple[int, datetime | None]]:
    """Return photos ordered by date (undated last), then id."""
    return sorted(photos, key=lambda item: (item[1] or datetime.max, item[0]))


def partition_by_date(
    photos: list[tuple[int, datetime | None]],
    page_count: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    weights: GroupingWeights | None = None,
) -> list[list[int]]:
    """Partition photos into ``page_count`` balanced, date-aware pages.

    Args:
        photos: ``(photo_id, captured_at)`` pairs. Undated photos sort last.
        page_count: Number of pages to produce.
        minimum: Optional soft minimum page size.
        maximum: Optional soft maximum page size.
        weights: Penalty weights; defaults to :class:`GroupingWeights`.

    Returns:
        A list of ``page_count`` lists of photo ids. Empty pages are returned
        when there are fewer photos than pages.
    """
    weights = weights or GroupingWeights()
    ordered = _build_sort_key(photos)
    n = len(ordered)
    p_total = max(0, page_count)

    if p_total == 0:
        return []
    if n == 0:
        return [[] for _ in range(p_total)]

    days = [_as_date(captured) for _photo_id, captured in ordered]
    gaps = _gap_values(days)
    dp, choice = _solve(
        ordered,
        days,
        gaps,
        n,
        p_total,
        minimum,
        maximum,
        weights,
    )

    groups: list[list[int]] = []
    p = p_total
    i = n
    while p > 0:
        size = choice[p][i]
        start = i - size
        groups.append([photo_id for photo_id, _ in ordered[start:i]])
        i = start
        p -= 1
    groups.reverse()
    return groups


def _gap_values(days: list[date | None]) -> list[int]:
    """Return the empty-day gap before each photo (index 0 is always zero)."""
    gaps = [0] * len(days)
    for index in range(1, len(days)):
        previous = days[index - 1]
        current = days[index]
        if previous is None or current is None:
            gaps[index] = 0
            continue
        gaps[index] = max(0, (current - previous).days - 1)
    return gaps


def _band_width(target: float) -> int:
    """Return the half-width of the candidate page-size band around a target."""
    if target <= 0:
        return 2
    return max(2, int(target + 0.999999))


def _solve(
    ordered: list[tuple[int, datetime | None]],
    days: list[date | None],
    gaps: list[int],
    n: int,
    p_total: int,
    minimum: int | None,
    maximum: int | None,
    weights: GroupingWeights,
) -> tuple[list[list[float]], list[list[int]]]:
    """Run the banded dynamic program and return cost and choice tables."""
    # Prefix sums let the segment cost be evaluated in O(1).
    gap_prefix = [0] * (n + 1)
    for index in range(n):
        gap_prefix[index + 1] = gap_prefix[index] + gaps[index]

    infinity = float("inf")
    dp = [[infinity] * (n + 1) for _ in range(p_total + 1)]
    choice = [[0] * (n + 1) for _ in range(p_total + 1)]
    dp[0][0] = 0.0

    large = n > _LARGE_INPUT_THRESHOLD
    allow_empty = n < p_total
    base_band = _LARGE_BAND if large else 0

    for p in range(1, p_total + 1):
        remaining_pages = p_total - p + 1
        # State ``(p, i)``: the first ``i`` photos are split across ``p`` pages.
        # ``j`` photos were consumed by the earlier ``p - 1`` pages, so the
        # moving target for the current page is ``(n - j) / remaining_pages``.
        min_i = 0 if allow_empty else p - 1
        max_i = n - (p_total - p)
        for i in range(min_i, max_i + 1):
            best_cost = infinity
            best_size = 1
            # Earlier pages can consume at most ``i`` photos here; when there
            # are fewer photos than pages a page may be empty (size 0).
            j_max = i
            j_min = max(p - 1, i - _max_page_size(n, p_total, minimum, maximum, base_band))
            for j in range(j_max, j_min - 1, -1):
                if dp[p - 1][j] == infinity:
                    continue
                size = i - j
                if allow_empty:
                    # Only constrain the upper size when a non-empty page would
                    # overshoot the moving target; a size of 0 (empty page) is
                    # always allowed so trailing pages can stay empty.
                    target = (n - j) / remaining_pages
                    band = max(_band_width(target), base_band)
                    if size > 0 and size > int(target + band) + 1:
                        continue
                else:
                    if size < 1:
                        continue
                    target = (n - j) / remaining_pages
                    band = max(_band_width(target), base_band)
                    if size < max(1, int(target - band)) or size > int(target + band) + 1:
                        continue
                cost = dp[p - 1][j] + _segment_cost(
                    ordered,
                    days,
                    gaps,
                    gap_prefix,
                    j,
                    i,
                    size,
                    target,
                    minimum,
                    maximum,
                    weights,
                )
                if cost < best_cost:
                    best_cost = cost
                    best_size = size
            dp[p][i] = best_cost
            choice[p][i] = best_size
    return dp, choice


def _max_page_size(
    n: int,
    p_total: int,
    minimum: int | None,
    maximum: int | None,
    base_band: int,
) -> int:
    """Return an upper bound on a single page size for the DP search."""
    target = n / p_total if p_total else n
    bound = int(target) + max(_band_width(target), base_band) + 1
    if maximum is not None:
        bound = max(bound, maximum + 1)
    return max(1, min(bound, n))


def _segment_cost(
    ordered: list[tuple[int, datetime | None]],
    days: list[date | None],
    gaps: list[int],
    gap_prefix: list[int],
    start: int,
    end: int,
    size: int,
    target: float,
    minimum: int | None,
    maximum: int | None,
    weights: GroupingWeights,
) -> float:
    """Return the cost of assigning ``ordered[start:end]`` to one page."""
    cost = weights.deviation_weight * (size - target) ** 2

    # Sum of gaps inside the segment (excluding the boundary before ``start``).
    internal_gap = gap_prefix[end] - gap_prefix[start + 1] if end > start + 1 else 0
    cost += weights.gap_weight * internal_gap

    if start > 0 and days[start] is not None and days[start] == days[start - 1]:
        cost += weights.split_weight

    if minimum is not None and size < minimum:
        cost += weights.below_min_weight * (minimum - size) ** 2
    if maximum is not None and size > maximum:
        cost += weights.above_max_weight * (size - maximum) ** 2

    return cost


__all__ = ["GroupingWeights", "partition_by_date"]
