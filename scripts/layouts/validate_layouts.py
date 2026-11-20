"""Validate layout YAML files and generate row-based tile templates.

Run from the repository root:

    uv run python scripts/layouts/validate_layouts.py --check
    uv run python scripts/layouts/validate_layouts.py --write-row-templates
    uv run python scripts/layouts/validate_layouts.py --path path/to/layout.yaml

The validator enforces the layout contract used by
:class:`photo_composition_designer.render.slot_renderer.SlotAwareRenderer`:

* the slots must tile the full normalized page exactly: no uncovered area and
  no overlaps;
* every pair of slots that the renderer treats as neighbours must receive a
  visible spacing gutter after pixel rounding and the renderer's edge insets.

The renderer rounds slot edges to pixels and insets each side that has a
neighbour by half the spacing gutter. If a pair of slots is *not* recognised
as neighbours, no inset is applied and the rendered images touch directly.
The second check simulates that behaviour, including the renderer's
normalized neighbour tolerance.

Use ``--neighbour-tol`` to reproduce the old ``1e-9`` renderer behaviour::

    uv run python scripts/layouts/validate_layouts.py \
        --path legacy.yaml --neighbour-tol 1e-9

Layouts shipped by this repository must pack the page edge-to-edge with zero
normalized gaps. The spacing gutter is created exclusively by the renderer.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
BUILTIN_LAYOUTS = ROOT / "src/photo_composition_designer/layouts/layouts"
DEFAULT_DPI = 300
DEFAULT_PAGE_WIDTH_MM = 216.0
DEFAULT_PAGE_HEIGHT_MM = 154.0

#: Must match :data:`photo_composition_designer.render.slot_renderer._NEIGHBOUR_TOLERANCE`.
RENDERER_NEIGHBOUR_TOLERANCE = 1e-4
#: Floating-point slack for geometry comparisons in the validator itself.
GEOM_EPS = 1e-7


@dataclass(frozen=True)
class RawSlot:
    """Minimal slot shape needed for geometry checks."""

    key: str
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        """Right edge in normalized coordinates."""
        return self.x + self.width

    @property
    def bottom(self) -> float:
        """Bottom edge in normalized coordinates."""
        return self.y + self.height


@dataclass
class Issue:
    """One validation finding."""

    layout: str
    severity: str
    slot: str
    message: str


@dataclass
class Report:
    """Aggregated validation result for one or more layouts."""

    issues: list[Issue] = field(default_factory=list)

    def add(self, layout: str, severity: str, slot: str, message: str) -> None:
        """Append one finding."""
        self.issues.append(Issue(layout=layout, severity=severity, slot=slot, message=message))

    def has_errors(self) -> bool:
        """Return whether the report contains at least one error."""
        return any(issue.severity == "error" for issue in self.issues)


def load_layout(path: Path) -> dict:
    """Load a YAML layout file as a raw mapping."""
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level mapping expected")
    return data


def raw_slots(data: dict, *, layout_key: str) -> list[RawSlot]:
    """Convert raw slot dicts into :class:`RawSlot` objects."""
    slots: list[RawSlot] = []
    for index, raw in enumerate(data.get("slots") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"{layout_key}: slot {index} must be a mapping")
        key = str(raw.get("key", f"slot_{index}"))
        slots.append(
            RawSlot(
                key=key,
                x=float(raw.get("x", 0.0)),
                y=float(raw.get("y", 0.0)),
                width=float(raw.get("width", 0.0)),
                height=float(raw.get("height", 0.0)),
            )
        )
    return slots


def _ranges_overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    """Return whether two 1-D ranges overlap by more than floating-point noise."""
    return min(a1, b1) - max(a0, b0) > GEOM_EPS


def _touches(a: RawSlot, b: RawSlot, side: str, tolerance: float) -> bool:
    """Mirror the renderer's normalized neighbour check for one side."""
    if side == "left":
        return (
            abs((b.x + b.width) - a.x) < tolerance
            and min(b.y + b.height, a.y + a.height) - max(b.y, a.y) > GEOM_EPS
        )
    if side == "right":
        return (
            abs((a.x + a.width) - b.x) < tolerance
            and min(a.y + a.height, b.y + b.height) - max(a.y, b.y) > GEOM_EPS
        )
    if side == "top":
        return (
            abs((b.y + b.height) - a.y) < tolerance
            and min(b.x + b.width, a.x + a.width) - max(b.x, a.x) > GEOM_EPS
        )
    return (
        abs((a.y + a.height) - b.y) < tolerance
        and min(a.x + a.width, b.x + b.width) - max(a.x, b.x) > GEOM_EPS
    )


def _has_neighbour(slots: list[RawSlot], slot: RawSlot, side: str, tolerance: float) -> bool:
    """Return whether the renderer would detect a neighbour on ``side``."""
    return any(other is not slot and _touches(slot, other, side, tolerance) for other in slots)


def _check_tiling(report: Report, layout_key: str, slots: list[RawSlot]) -> None:
    """Check that the slots tile the normalized page exactly.

    The check builds the elementary grid from all slot edges. Every grid cell
    must be covered by exactly one slot. This catches uncovered gaps and
    overlaps independently of row structure, so general layouts such as
    ``four_quadrants`` or ``five_split_center`` remain valid.
    """
    xs = sorted({0.0, 1.0} | {slot.x for slot in slots} | {slot.right for slot in slots})
    ys = sorted({0.0, 1.0} | {slot.y for slot in slots} | {slot.bottom for slot in slots})

    uncovered: list[tuple[float, float, float, float]] = []
    overlap_pairs: set[tuple[str, str]] = set()

    for x0, x1 in zip(xs, xs[1:]):
        if x1 - x0 <= GEOM_EPS:
            continue
        for y0, y1 in zip(ys, ys[1:]):
            if y1 - y0 <= GEOM_EPS:
                continue
            center_x = (x0 + x1) / 2.0
            center_y = (y0 + y1) / 2.0
            covering = [
                slot
                for slot in slots
                if slot.x < center_x < slot.right and slot.y < center_y < slot.bottom
            ]
            if not covering:
                uncovered.append((x0, x1, y0, y1))
            elif len(covering) > 1:
                for index, first in enumerate(covering):
                    for second in covering[index + 1 :]:
                        overlap_pairs.add(tuple(sorted((first.key, second.key))))

    if uncovered:
        total_area = sum((x1 - x0) * (y1 - y0) for x0, x1, y0, y1 in uncovered)
        first_x0, first_x1, first_y0, first_y1 = uncovered[0]
        report.add(
            layout_key,
            "error",
            "*",
            (
                f"{len(uncovered)} uncovered region(s) totalling {total_area:.6f} "
                f"normalized area; first at x=[{first_x0:.6f}, {first_x1:.6f}] "
                f"y=[{first_y0:.6f}, {first_y1:.6f}]"
            ),
        )

    for first_key, second_key in sorted(overlap_pairs):
        report.add(
            layout_key,
            "error",
            f"{first_key}/{second_key}",
            "slots overlap in the normalized tiling",
        )


def _check_spacing(
    report: Report,
    layout_key: str,
    slots: list[RawSlot],
    *,
    page_width: int,
    page_height: int,
    spacing_px: int,
    min_gap_px: int,
    tolerance: float,
) -> None:
    """Simulate the renderer's insets and report collapsed spacing gaps."""
    before = spacing_px // 2
    after = spacing_px - before
    # Pairs closer than one pixel are checked even when the renderer's
    # normalized tolerance does not classify them as neighbours. Otherwise a
    # sub-pixel rounding gap would slip through as an unreported visual touch.
    horizontal_pair_tol = max(tolerance, 1.0 / max(page_width, 1))
    vertical_pair_tol = max(tolerance, 1.0 / max(page_height, 1))

    for index, first in enumerate(slots):
        for second in slots[index + 1 :]:
            # Horizontal neighbours: one slot starts where the other ends.
            if _ranges_overlap(first.y, first.bottom, second.y, second.bottom) and (
                abs(first.right - second.x) < horizontal_pair_tol
                or abs(second.right - first.x) < horizontal_pair_tol
            ):
                if first.x <= second.x:
                    left, right = first, second
                else:
                    left, right = second, first
                left_has_neighbour = _has_neighbour(slots, left, "right", tolerance)
                right_has_neighbour = _has_neighbour(slots, right, "left", tolerance)
                left_edge = round(left.right * page_width) - (before if left_has_neighbour else 0)
                right_edge = round(right.x * page_width) + (after if right_has_neighbour else 0)
                pixel_gap = right_edge - left_edge
                if pixel_gap < min_gap_px:
                    report.add(
                        layout_key,
                        "error",
                        f"{left.key}->{right.key}",
                        (
                            f"horizontal gap collapses to {pixel_gap}px "
                            f"(required >= {min_gap_px}px); "
                            f"neighbours: left.right={left_has_neighbour}, "
                            f"right.left={right_has_neighbour}"
                        ),
                    )

            # Vertical neighbours: one slot starts where the other ends.
            if _ranges_overlap(first.x, first.right, second.x, second.right) and (
                abs(first.bottom - second.y) < vertical_pair_tol
                or abs(second.bottom - first.y) < vertical_pair_tol
            ):
                if first.y <= second.y:
                    upper, lower = first, second
                else:
                    upper, lower = second, first
                upper_has_neighbour = _has_neighbour(slots, upper, "bottom", tolerance)
                lower_has_neighbour = _has_neighbour(slots, lower, "top", tolerance)
                upper_edge = round(upper.bottom * page_height) - (
                    before if upper_has_neighbour else 0
                )
                lower_edge = round(lower.y * page_height) + (after if lower_has_neighbour else 0)
                pixel_gap = lower_edge - upper_edge
                if pixel_gap < min_gap_px:
                    report.add(
                        layout_key,
                        "error",
                        f"{upper.key}->{lower.key}",
                        (
                            f"vertical gap collapses to {pixel_gap}px "
                            f"(required >= {min_gap_px}px); "
                            f"neighbours: upper.bottom={upper_has_neighbour}, "
                            f"lower.top={lower_has_neighbour}"
                        ),
                    )


def validate_layout(
    path: Path,
    *,
    page_width: int,
    page_height: int,
    spacing_px: int,
    min_gap_px: int,
    neighbour_tol: float = RENDERER_NEIGHBOUR_TOLERANCE,
) -> Report:
    """Validate one layout file against the renderer geometry."""
    report = Report()
    key = path.stem
    try:
        data = load_layout(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        report.add(key, "error", "*", f"cannot load: {exc}")
        return report

    declared_key = str(data.get("key", key))
    if declared_key != key:
        report.add(
            declared_key,
            "warning",
            "*",
            f"file name {path.name!r} does not match key {declared_key!r}",
        )

    try:
        slots = raw_slots(data, layout_key=declared_key)
    except ValueError as exc:
        report.add(declared_key, "error", "*", str(exc))
        return report

    if not slots:
        report.add(declared_key, "error", "*", "layout declares no slots")
        return report

    # Bounds and degenerate geometry.
    for slot in slots:
        if not (0 <= slot.x <= 1 and 0 <= slot.y <= 1):
            report.add(declared_key, "error", slot.key, "origin outside [0,1]")
        if not (0 < slot.width <= 1 and 0 < slot.height <= 1):
            report.add(declared_key, "error", slot.key, "degenerate width/height")
        if slot.right > 1 + GEOM_EPS or slot.bottom > 1 + GEOM_EPS:
            report.add(declared_key, "error", slot.key, "slot exceeds layout bounds")
        if slot.width * page_width < 4 or slot.height * page_height < 4:
            report.add(
                declared_key,
                "error",
                slot.key,
                f"slot smaller than 4x4 px at {page_width}x{page_height}",
            )

    # Exact tiling: no uncovered area, no overlaps.
    _check_tiling(report, declared_key, slots)

    # Renderer spacing simulation.
    _check_spacing(
        report,
        declared_key,
        slots,
        page_width=page_width,
        page_height=page_height,
        spacing_px=spacing_px,
        min_gap_px=min_gap_px,
        tolerance=neighbour_tol,
    )

    return report


def iter_yaml_files(targets: list[Path]) -> list[Path]:
    """Expand a mix of files and directories into YAML layout files."""
    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            files.extend(sorted(target.glob("*.yaml")))
        else:
            files.append(target)
    return files


def page_dimensions(mm_width: float, mm_height: float, dpi: int) -> tuple[int, int]:
    """Return pixel page size for a millimetre page size."""
    return round(mm_width / 25.4 * dpi), round(mm_height / 25.4 * dpi)


# ---------------------------------------------------------------------------
# Row-based tile templates
# ---------------------------------------------------------------------------

# Each template is defined as (columns per row, row heights). Row heights are
# normalized and sum to 1.0. Columns per row are explicit so mixed templates
# remain valid. The generator lays out each row edge-to-edge with zero
# normalized gaps; the renderer creates the spacing gutter.
_ROW_TEMPLATES: dict[str, dict[str, tuple[float, ...]]] = {
    # 3 rows: fixed 4-col and 5-col, plus a 3-4-5 mixed with 40-35-25 heights.
    "tiles_3_rows_4col": {
        "columns": (4, 4, 4),
        "heights": (1 / 3, 1 / 3, 1 / 3),
    },
    "tiles_3_rows_5col": {
        "columns": (5, 5, 5),
        "heights": (1 / 3, 1 / 3, 1 / 3),
    },
    "tiles_3_rows_mixed": {
        "columns": (3, 4, 5),
        "heights": (0.40, 0.35, 0.25),
    },
    # 4 rows: fixed 5-col and 6-col, plus a 6-7-5-6 mixed with equal heights.
    "tiles_4_rows_5col": {
        "columns": (5, 5, 5, 5),
        "heights": (0.25, 0.25, 0.25, 0.25),
    },
    "tiles_4_rows_6col": {
        "columns": (6, 6, 6, 6),
        "heights": (0.25, 0.25, 0.25, 0.25),
    },
    "tiles_4_rows_mixed": {
        "columns": (6, 7, 5, 6),
        "heights": (0.25, 0.25, 0.25, 0.25),
    },
    # 5 rows: fixed 5-col and 6-col, plus a 6-7-5-6-7 mixed with equal heights.
    "tiles_5_rows_5col": {
        "columns": (5, 5, 5, 5, 5),
        "heights": (0.2, 0.2, 0.2, 0.2, 0.2),
    },
    "tiles_5_rows_6col": {
        "columns": (6, 6, 6, 6, 6),
        "heights": (0.2, 0.2, 0.2, 0.2, 0.2),
    },
    "tiles_5_rows_mixed": {
        "columns": (6, 7, 5, 6, 7),
        "heights": (0.2, 0.2, 0.2, 0.2, 0.2),
    },
}

_NAME_OVERRIDES: dict[str, str] = {
    "tiles_3_rows_4col": "Tiles 3 rows 4 columns",
    "tiles_3_rows_5col": "Tiles 3 rows 5 columns",
    "tiles_3_rows_mixed": "Tiles 3 rows mixed (3-4-5)",
    "tiles_4_rows_5col": "Tiles 4 rows 5 columns",
    "tiles_4_rows_6col": "Tiles 4 rows 6 columns",
    "tiles_4_rows_mixed": "Tiles 4 rows mixed (6-7-5-6)",
    "tiles_5_rows_5col": "Tiles 5 rows 5 columns",
    "tiles_5_rows_6col": "Tiles 5 rows 6 columns",
    "tiles_5_rows_mixed": "Tiles 5 rows mixed (6-7-5-6-7)",
}


def _partition(total: float, parts: int) -> list[float]:
    """Return ``parts + 1`` rounded edges from 0 to ``total``.

    Rounding the edges first and deriving each width from the neighbouring
    edges guarantees exact decimal adjacency: ``x + width`` equals the next
    edge without accumulating rounding drift.
    """
    edges = [round(index * total / parts, 6) for index in range(parts + 1)]
    edges[0] = 0.0
    edges[-1] = total
    return edges


def _height_edges(heights: tuple[float, ...]) -> list[float]:
    """Return rounded cumulative y edges for the given row heights."""
    edges = [0.0]
    accumulated = 0.0
    for height in heights:
        accumulated += height
        edges.append(round(accumulated, 6))
    edges[-1] = 1.0
    return edges


def generate_row_template(key: str) -> dict:
    """Generate a normalized row-based layout definition.

    Each row is laid out edge-to-edge: the first slot starts at x=0, every slot
    ends exactly where the next begins, and the last slot ends at x=1. Row
    heights follow the same edge-to-edge rule so consecutive rows touch. This
    is required for :class:`SlotAwareRenderer` to insert the spacing gutter;
    any positive normalized gap would instead be pasted over by the next slot.
    """
    spec = _ROW_TEMPLATES[key]
    columns = spec["columns"]
    heights = spec["heights"]
    if len(columns) != len(heights):
        raise ValueError(f"{key}: columns and heights length mismatch")

    y_edges = _height_edges(heights)
    slots: list[dict] = []
    for row_index, ncols in enumerate(columns):
        x_edges = _partition(1.0, ncols)
        y0 = y_edges[row_index]
        y1 = y_edges[row_index + 1]
        for col_index in range(ncols):
            x0 = x_edges[col_index]
            x1 = x_edges[col_index + 1]
            slots.append(
                {
                    "key": f"r{len(slots) + 1:02d}",
                    "x": round(x0, 6),
                    "y": round(y0, 6),
                    "width": round(x1 - x0, 6),
                    "height": round(y1 - y0, 6),
                    "crop_mode": "cover",
                }
            )
    return {
        "key": key,
        "version": 1,
        "name": _NAME_OVERRIDES.get(key, key.replace("_", " ").title()),
        "slots": slots,
    }


def write_row_templates(target_dir: Path, *, dry_run: bool = False) -> list[Path]:
    """Write the new row-based template YAML files.

    Existing files with the same key are replaced only when their content differs.
    Returns the list of written paths.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for key in _ROW_TEMPLATES:
        data = generate_row_template(key)
        path = target_dir / f"{key}.yaml"
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        if not dry_run:
            path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate layout YAMLs against renderer spacing geometry."
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="YAML file or directory to validate. Repeatable. Defaults to built-in layouts.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate and exit non-zero on errors.",
    )
    parser.add_argument(
        "--write-row-templates",
        action="store_true",
        help="Write the new row-based templates into the built-in layouts directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --write-row-templates: only report what would be written.",
    )
    parser.add_argument(
        "--neighbour-tol",
        type=float,
        default=RENDERER_NEIGHBOUR_TOLERANCE,
        help=(
            "Normalized neighbour tolerance used by the renderer "
            f"(default: {RENDERER_NEIGHBOUR_TOLERANCE})."
        ),
    )
    parser.add_argument(
        "--min-gap-px",
        type=int,
        default=None,
        help="Minimum pixel gap after insets (default: 1 when spacing > 0, else 0).",
    )
    parser.add_argument(
        "--width-mm",
        type=float,
        default=DEFAULT_PAGE_WIDTH_MM,
        help=f"Page width in mm (default: {DEFAULT_PAGE_WIDTH_MM}).",
    )
    parser.add_argument(
        "--height-mm",
        type=float,
        default=DEFAULT_PAGE_HEIGHT_MM,
        help=f"Page height in mm (default: {DEFAULT_PAGE_HEIGHT_MM}).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"Render DPI (default: {DEFAULT_DPI}).",
    )
    parser.add_argument(
        "--spacing-mm",
        type=float,
        default=2.0,
        help="Layout spacing in mm (default: 2).",
    )
    args = parser.parse_args()

    width_px, height_px = page_dimensions(args.width_mm, args.height_mm, args.dpi)
    spacing_px = round(args.spacing_mm / 25.4 * args.dpi)
    min_gap_px = args.min_gap_px
    if min_gap_px is None:
        min_gap_px = 1 if spacing_px > 0 else 0

    if args.write_row_templates:
        written = write_row_templates(BUILTIN_LAYOUTS, dry_run=args.dry_run)
        for path in written:
            print(f"write {path.relative_to(ROOT)}")
        return 0

    targets = [Path(p) for p in args.path] if args.path else [BUILTIN_LAYOUTS]
    files = iter_yaml_files(targets)
    if not files:
        print("no YAML files found", file=sys.stderr)
        return 2

    reports = [
        validate_layout(
            path,
            page_width=width_px,
            page_height=height_px,
            spacing_px=spacing_px,
            min_gap_px=min_gap_px,
            neighbour_tol=args.neighbour_tol,
        )
        for path in files
    ]

    errors = 0
    warnings = 0
    for report in reports:
        for issue in report.issues:
            prefix = "ERROR" if issue.severity == "error" else "WARN "
            location = f"{issue.layout}:{issue.slot}"
            print(f"{prefix} {location}: {issue.message}")
            if issue.severity == "error":
                errors += 1
            else:
                warnings += 1

    total_slots = sum(
        len(raw_slots(load_layout(path), layout_key=path.stem)) for path in files if path.exists()
    )
    print(
        f"\n{len(files)} layout(s), {total_slots} slots, "
        f"{errors} error(s), {warnings} warning(s) "
        f"at {width_px}x{height_px}px, spacing={spacing_px}px, "
        f"neighbour_tol={args.neighbour_tol:g}"
    )

    if args.check and errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
