"""Tests for the pure date-aware grouping dynamic program."""

from __future__ import annotations

from datetime import datetime, timedelta

from photo_composition_designer.project.date_grouping import (
    GroupingWeights,
    partition_by_date,
)


def _sizes(groups: list[list[int]]) -> list[int]:
    return [len(group) for group in groups]


def test_twelve_same_day_photos_split_into_balanced_pages() -> None:
    day = datetime(2027, 1, 4)
    groups = partition_by_date([(index, day) for index in range(12)], 2)
    assert _sizes(groups) == [6, 6]


def test_ten_same_day_photos_split_into_balanced_pages() -> None:
    day = datetime(2027, 1, 4)
    groups = partition_by_date([(index, day) for index in range(10)], 2)
    assert _sizes(groups) == [5, 5]


def test_seven_same_day_photos_split_with_a_single_day_penalty() -> None:
    day = datetime(2027, 1, 4)
    groups = partition_by_date([(index, day) for index in range(7)], 2)
    # One split is charged; the sizes stay balanced because the split penalty
    # (6) is smaller than the deviation cost of a 7/0 split.
    assert _sizes(groups) == [4, 3]


def test_consecutive_days_are_balanced() -> None:
    day = datetime(2027, 1, 4)
    photos = [(index, day + timedelta(days=index // 2)) for index in range(12)]
    groups = partition_by_date(photos, 2)
    assert _sizes(groups) == [6, 6]


def test_large_date_gap_starts_a_new_page() -> None:
    day = datetime(2027, 1, 4)
    photos = [
        (0, day),
        (1, day),
        (2, day),
        (3, day + timedelta(days=10)),
        (4, day + timedelta(days=10)),
        (5, day + timedelta(days=10)),
    ]
    groups = partition_by_date(photos, 2)
    assert _sizes(groups) == [3, 3]
    assert set(groups[0]) == {0, 1, 2}
    assert set(groups[1]) == {3, 4, 5}


def test_assignment_is_complete_and_deterministic() -> None:
    day = datetime(2027, 1, 4)
    photos = [(index, day + timedelta(days=index % 3)) for index in range(30)]
    first = partition_by_date(photos, 5)
    second = partition_by_date(photos, 5)
    assert first == second
    flat = [photo_id for group in first for photo_id in group]
    assert sorted(flat) == list(range(30))


def test_soft_bounds_penalise_out_of_range_pages() -> None:
    day = datetime(2027, 1, 4)
    photos = [(index, day + timedelta(days=index // 2)) for index in range(20)]
    groups = partition_by_date(photos, 4, minimum=4, maximum=6, weights=GroupingWeights())
    assert all(4 <= size <= 6 for size in _sizes(groups))


def test_more_pages_than_photos_assigns_every_photo() -> None:
    day = datetime(2027, 1, 4)
    groups = partition_by_date([(0, day), (1, day)], 4)
    # Pages may be empty when there are fewer photos than pages, but every
    # photo must still be assigned exactly once.
    assert sorted(photo_id for group in groups for photo_id in group) == [0, 1]
    assert sum(_sizes(groups)) == 2
