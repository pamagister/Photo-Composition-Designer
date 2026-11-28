"""Tests for the pure, deterministic automatic collage layout engine."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from photo_composition_designer.layouts import auto_layout
from photo_composition_designer.layouts.auto_layout import (
    AutoPhoto,
    AutoSlot,
    build_auto_layout,
)

TOL = 1e-9


def _landscape(key: str, importance: float = 1.0) -> AutoPhoto:
    """A FULL HD landscape photo (aspect 16:9)."""
    return AutoPhoto(key=key, width=1920, height=1080, importance=importance)


def _portrait(key: str, importance: float = 1.0) -> AutoPhoto:
    """A 3:4 portrait photo."""
    return AutoPhoto(key=key, width=1200, height=1600, importance=importance)


def _coverage_and_overlap(slots: tuple[AutoSlot, ...]) -> tuple[float, float]:
    """Return total covered area and maximum pairwise overlap area."""
    coverage = sum(slot.width * slot.height for slot in slots)
    max_overlap = 0.0
    for i, first in enumerate(slots):
        for second in slots[i + 1 :]:
            overlap_w = max(
                0.0, min(first.x + first.width, second.x + second.width) - max(first.x, second.x)
            )
            overlap_h = max(
                0.0, min(first.y + first.height, second.y + second.height) - max(first.y, second.y)
            )
            max_overlap = max(max_overlap, overlap_w * overlap_h)
    return coverage, max_overlap


def test_one_photo_fills_the_canvas() -> None:
    for aspect in (0.5, 1.0, 1.5, 1.78, 2.4):
        slots = build_auto_layout([_landscape("a")], aspect)
        assert len(slots) == 1
        slot = slots[0]
        assert (slot.x, slot.y) == (0.0, 0.0)
        assert slot.width == pytest.approx(1.0)
        assert slot.height == pytest.approx(1.0)


def test_two_landscapes_split_side_by_side_on_landscape_canvas() -> None:
    slots = build_auto_layout([_landscape("a"), _landscape("b")], 1.78)
    assert len(slots) == 2
    for slot in slots:
        assert slot.y == pytest.approx(0.0)
        assert slot.height == pytest.approx(1.0)
    assert slots[0].x == pytest.approx(0.0)
    assert slots[1].x == pytest.approx(0.5)


def test_two_landscapes_stack_on_portrait_canvas() -> None:
    slots = build_auto_layout([_landscape("a"), _landscape("b")], 0.5)
    assert len(slots) == 2
    for slot in slots:
        assert slot.x == pytest.approx(0.0)
        assert slot.width == pytest.approx(1.0)
    assert slots[0].y == pytest.approx(0.0)
    assert slots[1].y == pytest.approx(0.5)


def test_two_portraits_split_side_by_side_on_landscape_canvas() -> None:
    slots = build_auto_layout([_portrait("a"), _portrait("b")], 1.78)
    assert len(slots) == 2
    for slot in slots:
        assert slot.y == pytest.approx(0.0)
        assert slot.height == pytest.approx(1.0)
    assert slots[0].x == pytest.approx(0.0)
    assert slots[1].x == pytest.approx(0.5)


def test_portrait_plus_two_landscapes_puts_portrait_on_one_side() -> None:
    slots = build_auto_layout([_portrait("p"), _landscape("a"), _landscape("b")], 1.78)
    assert len(slots) == 3

    portrait = slots[0]
    landscapes = slots[1:]
    # The portrait occupies the full height on one side.
    assert portrait.x == pytest.approx(0.0)
    assert portrait.height == pytest.approx(1.0)
    # The two landscapes are stacked next to it, sharing the same column.
    assert landscapes[0].x == pytest.approx(landscapes[1].x)
    assert landscapes[0].y == pytest.approx(0.0)
    assert landscapes[1].y == pytest.approx(0.5)
    assert landscapes[0].width == pytest.approx(landscapes[1].width)
    # Together the two columns fill the canvas.
    assert portrait.width + landscapes[0].width == pytest.approx(1.0)


@pytest.mark.parametrize("aspect", [0.5, 1.0, 1.5, 1.78, 2.4])
@pytest.mark.parametrize("count", list(range(1, 31)))
def test_tiling_is_exact_for_all_counts(aspect: float, count: int) -> None:
    photos: list[AutoPhoto] = []
    for index in range(count):
        if index % 3 == 0:
            photos.append(AutoPhoto(key=str(index), width=1200, height=1600))
        elif index % 3 == 1:
            photos.append(AutoPhoto(key=str(index), width=1920, height=1080))
        else:
            photos.append(AutoPhoto(key=str(index), width=1000, height=1000))

    slots = build_auto_layout(photos, aspect)
    assert len(slots) == count
    assert [slot.key for slot in slots] == [f"auto_{i}" for i in range(count)]

    for slot in slots:
        assert -TOL <= slot.x <= 1.0 + TOL
        assert -TOL <= slot.y <= 1.0 + TOL
        assert slot.width > 0 and slot.height > 0
        assert slot.x + slot.width <= 1.0 + 1e-6
        assert slot.y + slot.height <= 1.0 + 1e-6

    coverage, overlap = _coverage_and_overlap(slots)
    assert coverage == pytest.approx(1.0, abs=1e-6)
    assert overlap == pytest.approx(0.0, abs=1e-6)


def test_deterministic_for_identical_input() -> None:
    photos = [_portrait("p"), _landscape("a"), _landscape("b"), _landscape("c")]
    first = build_auto_layout(photos, 1.78)
    second = build_auto_layout(photos, 1.78)
    assert first == second


def test_importance_weighting_changes_allocation() -> None:
    neutral = [_landscape("a"), _landscape("b")]
    weighted = [_landscape("a", 1.0), _landscape("b", 3.0)]

    plain = build_auto_layout(neutral, 1.78, importance_weight=0.0)
    assert plain[0].width == pytest.approx(plain[1].width)

    boosted = build_auto_layout(weighted, 1.78, importance_weight=1.0)
    assert boosted[1].width > boosted[0].width


def test_importance_weight_zero_ignores_importance() -> None:
    weighted = [_landscape("a", 1.0), _landscape("b", 5.0)]
    slots = build_auto_layout(weighted, 1.78, importance_weight=0.0)
    assert slots[0].width == pytest.approx(slots[1].width)


def test_empty_input_returns_empty_tuple() -> None:
    assert build_auto_layout([], 1.78) == ()


def test_invalid_canvas_aspect_raises() -> None:
    with pytest.raises(ValueError):
        build_auto_layout([_landscape("a")], 0.0)


def test_invalid_photo_dimensions_raise() -> None:
    with pytest.raises(ValueError):
        build_auto_layout([AutoPhoto(key="bad", width=0, height=100)], 1.78)


def test_builds_thirty_photos_under_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bound search work rather than elapsed time to avoid runner-load noise."""
    photos = [
        AutoPhoto(
            key=str(index),
            width=(1200, 1920, 1000)[index % 3],
            height=(1600, 1080, 1000)[index % 3],
            importance=1.0 + (index % 3) * 0.1,
        )
        for index in range(30)
    ]
    candidates_considered = 0
    original_candidates = auto_layout._Engine._candidates

    def count_candidates(
        engine: auto_layout._Engine,
        items: tuple[AutoPhoto, ...],
        aspect: float,
    ) -> Iterator[tuple[str, int, float, tuple[float, float]]]:
        nonlocal candidates_considered
        for candidate in original_candidates(engine, items, aspect):
            candidates_considered += 1
            yield candidate

    monkeypatch.setattr(auto_layout._Engine, "_candidates", count_candidates)
    slots = build_auto_layout(photos, 1.78)
    assert len(slots) == 30
    assert candidates_considered <= 50_000, (
        f"30-photo layout considered {candidates_considered:,} split candidates (budget 50,000)"
    )
