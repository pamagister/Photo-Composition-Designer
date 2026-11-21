"""Deterministic, content-aware automatic collage layout.

The engine turns an ordered list of photos and a canvas aspect ratio into a
normalized, full-bleed tiling of the collage content box. It performs no I/O,
uses no randomness and is deterministic: the same photo set and canvas aspect
always produce the same slots.

Algorithm
---------
Photos are ordered by orientation (portrait first, then square, then landscape)
while keeping the input order inside an orientation class. A memoised greedy
top-down search then finds the cheapest recursive split of that sequence into a
rectangular tiling:

* a ``row`` candidate puts every photo side by side,
* a ``column`` candidate stacks every photo,
* a binary split along ``x`` or ``y`` divides the sequence into two contiguous
  groups and allocates width (``x``) or height (``y``) proportionally to each
  group's preferred aspect ratio.

The cost of a candidate is the area-weighted absolute log-ratio between the
resulting cell aspect and the photo aspect, i.e. how much each photo has to be
cropped. A one-sided fairness penalty keeps a group from being starved of area.
Importance weights (an optional content score) bias the area allocation.

The search caches lightweight cost estimates; the render tree is materialised
once afterwards, which keeps the search fast even for 30 photos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Log-scale quantisation buckets per e-fold used to key the cost cache.
_ASPECT_BUCKETS = 12

#: ("leaf",) | ("row",) | ("col",) | ("split", axis, k, f1, left, right)
_Decision = tuple


@dataclass(frozen=True)
class AutoPhoto:
    """One photo fed into the automatic layout engine.

    Attributes:
        key: Stable identifier used to build the slot key. The engine emits
            slots named ``auto_0 … auto_{n-1}`` in reading order, so ``key`` is
            carried for callers that need to map back to a source photo.
        width: Pixel width of the photo.
        height: Pixel height of the photo.
        importance: Non-negative area weight. ``1.0`` means neutral.
    """

    key: str
    width: int
    height: int
    importance: float = 1.0

    @property
    def aspect(self) -> float:
        """Return the width-to-height aspect ratio of the photo."""
        return self.width / self.height


@dataclass(frozen=True)
class AutoSlot:
    """A normalized slot rectangle produced by :func:`build_auto_layout`."""

    key: str
    x: float
    y: float
    width: float
    height: float

    @property
    def aspect(self) -> float:
        """Return the width-to-height aspect ratio of the slot."""
        return self.width / self.height


@dataclass
class _Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def aspect(self) -> float:
        return self.w / self.h


@dataclass
class _Node:
    rect: _Rect
    photo: AutoPhoto | None = None
    children: list[_Node] | None = None


def _row_aspect(group: tuple[AutoPhoto, ...]) -> float:
    """Aspect ratio when every photo in the group sits side by side."""
    return sum(photo.aspect * photo.importance for photo in group)


def _col_aspect(group: tuple[AutoPhoto, ...]) -> float:
    """Aspect ratio when every photo in the group is stacked vertically."""
    return 1.0 / sum(photo.importance / photo.aspect for photo in group)


def _distortion(actual: float, wanted: float) -> float:
    """Absolute log-ratio between an actual and a wanted aspect ratio."""
    if actual <= 0 or wanted <= 0:
        return 50.0
    return abs(math.log(actual / wanted))


def _row_rects(group: tuple[AutoPhoto, ...]) -> list[_Rect]:
    total = _row_aspect(group) or 1.0
    rects: list[_Rect] = []
    x = 0.0
    for photo in group:
        width = photo.aspect * photo.importance / total
        rects.append(_Rect(x, 0.0, width, 1.0))
        x += width
    return rects


def _col_rects(group: tuple[AutoPhoto, ...]) -> list[_Rect]:
    total = sum(photo.importance / photo.aspect for photo in group) or 1.0
    rects: list[_Rect] = []
    y = 0.0
    for photo in group:
        height = (photo.importance / photo.aspect) / total
        rects.append(_Rect(0.0, y, 1.0, height))
        y += height
    return rects


def _quantize(aspect: float) -> int:
    """Log-scale quantisation used to key the cost cache."""
    return max(-60, min(60, int(round(math.log(max(aspect, 1e-6)) * _ASPECT_BUCKETS))))


def _dequantize(value: int) -> float:
    return math.exp(value / _ASPECT_BUCKETS)


class _Engine:
    """Stateful search over one photo set, parameterized by weights."""

    def __init__(self, balance_weight: float) -> None:
        self._balance_weight = balance_weight
        self._one_level_cache: dict[tuple[tuple[AutoPhoto, ...], int], float] = {}

    def _split_positions(self, items: tuple[AutoPhoto, ...]) -> list[int]:
        """Candidate split points: orientation changes plus balanced positions."""
        n = len(items)
        if n <= 8:
            return list(range(1, n))
        positions = {1, 2, 3, 4, n - 4, n - 3, n - 2, n - 1, n // 3, n // 2, 2 * n // 3}
        for index in range(1, n):
            if round(items[index - 1].aspect, 1) != round(items[index].aspect, 1):
                positions.add(index)
        return sorted(position for position in positions if 0 < position < n)

    def _fair_share(self, group: tuple[AutoPhoto, ...]) -> float:
        return sum(photo.importance for photo in group)

    def _balance_penalty(
        self, fraction: float, left: tuple[AutoPhoto, ...], items: tuple[AutoPhoto, ...]
    ) -> float:
        """Penalise groups that receive less area than their importance-weighted share.

        The penalty is one-sided on purpose: giving a small group more room than
        its fair share is acceptable, while starving a large group produces
        slivers.
        """
        total = self._fair_share(items)
        if total <= 0 or not 0.0 < fraction < 1.0:
            return 50.0
        fair = self._fair_share(left) / total
        return self._balance_weight * (
            max(0.0, math.log(fair / fraction))
            + max(0.0, math.log((1.0 - fair) / (1.0 - fraction)))
        )

    def _candidates(self, items: tuple[AutoPhoto, ...], aspect: float):
        """Yield ``(axis, k, f1, child_aspects)`` split candidates.

        ``f1`` is the width fraction (x split) or height fraction (y split)
        given to the left/top group. Four allocations are offered: aspect-derived
        row and column allocations, an equal split and an importance-proportional
        split.
        """
        total_fair = self._fair_share(items) or 1.0
        for axis in ("x", "y"):
            for k in self._split_positions(items):
                left, right = items[:k], items[k:]
                fractions: list[float] = []
                for variant in ("row", "col"):
                    p1 = _row_aspect(left) if variant == "row" else _col_aspect(left)
                    p2 = _row_aspect(right) if variant == "row" else _col_aspect(right)
                    if p1 <= 0 or p2 <= 0:
                        continue
                    if axis == "x":
                        fractions.append(p1 / (p1 + p2))
                    else:
                        inv1, inv2 = 1.0 / p1, 1.0 / p2
                        fractions.append(inv1 / (inv1 + inv2))
                fractions.append(0.5)
                fractions.append(self._fair_share(left) / total_fair)
                for fraction in fractions:
                    if not 0.0 < fraction < 1.0:
                        continue
                    if axis == "x":
                        child_aspects = (aspect * fraction, aspect * (1.0 - fraction))
                    else:
                        child_aspects = (aspect / fraction, aspect / (1.0 - fraction))
                    yield axis, k, fraction, child_aspects

    def _base_cost(self, items: tuple[AutoPhoto, ...], aspect: float) -> float:
        """Cost of arranging a group as a single row or a single column."""
        if len(items) == 1:
            return _distortion(aspect, items[0].aspect)
        return min(
            _distortion(aspect, _row_aspect(items)),
            _distortion(aspect, _col_aspect(items)),
        )

    def _one_level_cost(self, items: tuple[AutoPhoto, ...], aspect_q: int) -> float:
        """Estimate: best arrangement with at most one split level."""
        key = (items, aspect_q)
        cached = self._one_level_cache.get(key)
        if cached is not None:
            return cached
        aspect = _dequantize(aspect_q)
        if len(items) == 1:
            cost = _distortion(aspect, items[0].aspect)
        else:
            cost = self._base_cost(items, aspect)
            for _axis, k, fraction, child_aspects in self._candidates(items, aspect):
                left, right = items[:k], items[k:]
                cost = min(
                    cost,
                    fraction * self._base_cost(left, child_aspects[0])
                    + (1.0 - fraction) * self._base_cost(right, child_aspects[1])
                    + self._balance_penalty(fraction, left, items),
                )
        self._one_level_cache[key] = cost
        return cost

    def search(self, items: tuple[AutoPhoto, ...], aspect_q: int) -> tuple[_Decision, float]:
        """Greedy top-down search with a one-level lookahead.

        The cost is the area-weighted mean absolute log-ratio between each
        photo's cell aspect and the photo's own aspect (the real cropping
        distortion), plus an area-fairness term that keeps every photo at a
        sensible size.
        """
        aspect = _dequantize(aspect_q)
        if len(items) == 1:
            return ("leaf",), _distortion(aspect, items[0].aspect)

        best_decision: _Decision = ("row",)
        best_cost = _distortion(aspect, _row_aspect(items))

        col_cost = _distortion(aspect, _col_aspect(items))
        if col_cost < best_cost:
            best_cost = col_cost
            best_decision = ("col",)

        best_candidate = None
        for axis, k, fraction, child_aspects in self._candidates(items, aspect):
            left, right = items[:k], items[k:]
            left_q = _quantize(child_aspects[0])
            right_q = _quantize(child_aspects[1])
            total = (
                fraction * self._one_level_cost(left, left_q)
                + (1.0 - fraction) * self._one_level_cost(right, right_q)
                + self._balance_penalty(fraction, left, items)
            )
            if total < best_cost:
                best_cost = total
                best_candidate = (axis, k, fraction, left_q, right_q)
        if best_candidate is not None:
            axis, k, fraction, left_q, right_q = best_candidate
            left, right = items[:k], items[k:]
            left_decision, left_cost = self.search(left, left_q)
            right_decision, right_cost = self.search(right, right_q)
            best_decision = ("split", axis, k, fraction, left_decision, right_decision)
            best_cost = (
                fraction * left_cost
                + (1.0 - fraction) * right_cost
                + self._balance_penalty(fraction, left, items)
            )
        return best_decision, best_cost


def _child_rect(parent: _Rect, relative: _Rect) -> _Rect:
    return _Rect(
        parent.x + parent.w * relative.x,
        parent.y + parent.h * relative.y,
        parent.w * relative.w,
        parent.h * relative.h,
    )


def _materialise(items: tuple[AutoPhoto, ...], decision: _Decision, rect: _Rect) -> _Node:
    kind = decision[0]
    if kind == "leaf":
        return _Node(rect, photo=items[0])
    if kind == "row":
        return _Node(
            rect,
            children=[
                _Node(_child_rect(rect, rel), photo=photo)
                for rel, photo in zip(_row_rects(items), items)
            ],
        )
    if kind == "col":
        return _Node(
            rect,
            children=[
                _Node(_child_rect(rect, rel), photo=photo)
                for rel, photo in zip(_col_rects(items), items)
            ],
        )
    _, axis, k, fraction, left_decision, right_decision = decision
    if axis == "x":
        left_rel, right_rel = (
            _Rect(0.0, 0.0, fraction, 1.0),
            _Rect(fraction, 0.0, 1.0 - fraction, 1.0),
        )
    else:
        left_rel, right_rel = (
            _Rect(0.0, 0.0, 1.0, fraction),
            _Rect(0.0, fraction, 1.0, 1.0 - fraction),
        )
    return _Node(
        rect,
        children=[
            _materialise(items[:k], left_decision, _child_rect(rect, left_rel)),
            _materialise(items[k:], right_decision, _child_rect(rect, right_rel)),
        ],
    )


def _leaves(node: _Node) -> list[_Node]:
    if node.children is None:
        return [node]
    out: list[_Node] = []
    for child in node.children:
        out.extend(_leaves(child))
    return out


def order_photos(photos: list[AutoPhoto] | tuple[AutoPhoto, ...]) -> tuple[AutoPhoto, ...]:
    """Order photos by orientation (portrait, square, landscape).

    The input order is preserved inside an orientation class. This is the same
    ordering :func:`build_auto_layout` uses, exposed so callers can map the
    returned ``auto_<i>`` slots back to their source photos.
    """
    indexed = sorted(
        enumerate(photos),
        key=lambda pair: (round(pair[1].aspect, 2), pair[0]),
    )
    return tuple(photo for _, photo in indexed)


def build_auto_layout(
    photos: list[AutoPhoto] | tuple[AutoPhoto, ...],
    canvas_aspect: float,
    *,
    importance_weight: float = 1.0,
    balance_weight: float = 0.2,
) -> tuple[AutoSlot, ...]:
    """Build a deterministic, full-bleed tiling for ``photos``.

    Args:
        photos: Photos to arrange. Their order is preserved inside an
            orientation class (portrait, square, landscape).
        canvas_aspect: Width-to-height ratio of the collage content box.
        importance_weight: Scales how strongly per-photo ``importance`` biases
            the area allocation. ``0.0`` ignores importance; ``1.0`` (default)
            uses it as-is.
        balance_weight: Weight of the one-sided area-fairness penalty. ``0.0``
            disables it and allows slivers.

    Returns:
        Slots named ``auto_0 … auto_{n-1}`` in reading order (tree traversal:
        left-to-right then top-to-bottom). An empty input yields an empty tuple.
    """
    if canvas_aspect <= 0:
        raise ValueError("canvas_aspect must be positive")
    if not photos:
        return ()

    weighted: list[AutoPhoto] = []
    for photo in photos:
        if photo.width <= 0 or photo.height <= 0:
            raise ValueError(f"photo {photo.key!r} must have positive dimensions")
        effective = 1.0 + (max(photo.importance, 0.0) - 1.0) * importance_weight
        effective = max(effective, 1e-6)
        weighted.append(
            AutoPhoto(key=photo.key, width=photo.width, height=photo.height, importance=effective)
        )

    ordered = order_photos(tuple(weighted))
    engine = _Engine(balance_weight)
    decision, _cost = engine.search(ordered, _quantize(canvas_aspect))
    node = _materialise(ordered, decision, _Rect(0.0, 0.0, 1.0, 1.0))

    slots: list[AutoSlot] = []
    for index, leaf in enumerate(_leaves(node)):
        assert leaf.photo is not None
        rect = leaf.rect
        slots.append(
            AutoSlot(
                key=f"auto_{index}",
                x=rect.x,
                y=rect.y,
                width=rect.w,
                height=rect.h,
            )
        )
    return tuple(slots)
