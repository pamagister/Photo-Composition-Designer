"""Validate layout YAML files and generate row-based layout templates.

Run from the repository root:

    uv run python scripts/layouts_helper.py validate --check
    uv run python scripts/layouts_helper.py validate --path path/to/layout.yaml
    uv run python scripts/layouts_helper.py generate \
        --columns 4,3,5 --heights 30,40,30 --output path/to/layout.yaml
    uv run python scripts/layouts_helper.py write-templates

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

    uv run python scripts/layouts_helper.py validate \
        --path legacy.yaml --neighbour-tol 1e-9

Layouts shipped by this repository must pack the page edge-to-edge with zero
normalized gaps. The spacing gutter is created exclusively by the renderer.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
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


def validate_data(
    data: dict,
    *,
    key: str,
    file_name: str | None,
    page_width: int,
    page_height: int,
    spacing_px: int,
    min_gap_px: int,
    neighbour_tol: float = RENDERER_NEIGHBOUR_TOLERANCE,
) -> Report:
    """Validate a raw layout mapping against the renderer geometry."""
    report = Report()
    if not isinstance(data, dict):
        report.add(key, "error", "*", "top-level mapping expected")
        return report

    declared_key = str(data.get("key", key))
    if file_name is not None and declared_key != key:
        report.add(
            declared_key,
            "warning",
            "*",
            f"file name {file_name!r} does not match key {declared_key!r}",
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
    key = path.stem
    try:
        data = load_layout(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        report = Report()
        report.add(key, "error", "*", f"cannot load: {exc}")
        return report

    return validate_data(
        data,
        key=key,
        file_name=path.name,
        page_width=page_width,
        page_height=page_height,
        spacing_px=spacing_px,
        min_gap_px=min_gap_px,
        neighbour_tol=neighbour_tol,
    )


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
# Row-based layout generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RowTemplate:
    """Column counts, row height weights and display name of one template."""

    columns: tuple[int, ...]
    heights: tuple[float, ...]
    name: str


# Row heights are relative weights and are normalized to sum to 1.0. Columns
# per row are explicit so mixed templates remain valid. The generator lays out
# each row edge-to-edge with zero normalized gaps; the renderer creates the
# spacing gutter.
BUILTIN_ROW_TEMPLATES: dict[str, RowTemplate] = {
    # 3 rows: fixed 4-col and 5-col, plus a 3-4-5 mixed with 40-35-25 heights.
    "tiles_3_rows_4col": RowTemplate(
        columns=(4, 4, 4),
        heights=(1 / 3, 1 / 3, 1 / 3),
        name="Tiles 3 rows 4 columns",
    ),
    "tiles_3_rows_5col": RowTemplate(
        columns=(5, 5, 5),
        heights=(1 / 3, 1 / 3, 1 / 3),
        name="Tiles 3 rows 5 columns",
    ),
    "tiles_3_rows_mixed": RowTemplate(
        columns=(3, 4, 5),
        heights=(0.40, 0.35, 0.25),
        name="Tiles 3 rows mixed (3-4-5)",
    ),
    # 4 rows: fixed 5-col and 6-col, plus a 6-7-5-6 mixed with equal heights.
    "tiles_4_rows_5col": RowTemplate(
        columns=(5, 5, 5, 5),
        heights=(0.25, 0.25, 0.25, 0.25),
        name="Tiles 4 rows 5 columns",
    ),
    "tiles_4_rows_6col": RowTemplate(
        columns=(6, 6, 6, 6),
        heights=(0.25, 0.25, 0.25, 0.25),
        name="Tiles 4 rows 6 columns",
    ),
    "tiles_4_rows_mixed": RowTemplate(
        columns=(6, 7, 5, 6),
        heights=(0.25, 0.25, 0.25, 0.25),
        name="Tiles 4 rows mixed (6-7-5-6)",
    ),
    # 5 rows: fixed 5-col and 6-col, plus a 6-7-5-6-7 mixed with equal heights.
    "tiles_5_rows_5col": RowTemplate(
        columns=(5, 5, 5, 5, 5),
        heights=(0.2, 0.2, 0.2, 0.2, 0.2),
        name="Tiles 5 rows 5 columns",
    ),
    "tiles_5_rows_6col": RowTemplate(
        columns=(6, 6, 6, 6, 6),
        heights=(0.2, 0.2, 0.2, 0.2, 0.2),
        name="Tiles 5 rows 6 columns",
    ),
    "tiles_5_rows_mixed": RowTemplate(
        columns=(6, 7, 5, 6, 7),
        heights=(0.2, 0.2, 0.2, 0.2, 0.2),
        name="Tiles 5 rows mixed (6-7-5-6-7)",
    ),
}


def parse_columns(text: str) -> list[int]:
    """Parse a comma-separated list of positive column counts.

    Raises:
        ValueError: If a value is not an integer or is not positive.
    """
    try:
        columns = [int(part.strip()) for part in text.split(",")]
    except ValueError as exc:
        raise ValueError(f"columns must be comma-separated integers: {text!r}") from exc
    if not columns or any(count < 1 for count in columns):
        raise ValueError(f"every row needs at least one column: {text!r}")
    return columns


def parse_heights(text: str) -> list[float]:
    """Parse a comma-separated list of positive row height weights.

    Raises:
        ValueError: If a value is not a number or is not positive.
    """
    try:
        heights = [float(part.strip()) for part in text.split(",")]
    except ValueError as exc:
        raise ValueError(f"heights must be comma-separated numbers: {text!r}") from exc
    if not heights or any(height <= 0 for height in heights):
        raise ValueError(f"every row height must be positive: {text!r}")
    return heights


def normalize_weights(weights: Sequence[float]) -> list[float]:
    """Scale positive weights so they sum to 1.0.

    Raises:
        ValueError: If the weights are empty or do not have a positive sum.
    """
    if not weights:
        raise ValueError("at least one row is required")
    total = sum(weights)
    if total <= 0:
        raise ValueError("row heights must have a positive sum")
    return [weight / total for weight in weights]


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


def _height_edges(heights: Sequence[float]) -> list[float]:
    """Return rounded cumulative y edges for the given row heights."""
    edges = [0.0]
    accumulated = 0.0
    for height in heights:
        accumulated += height
        edges.append(round(accumulated, 6))
    edges[-1] = 1.0
    return edges


def build_row_layout(
    key: str,
    columns: Sequence[int],
    *,
    name: str | None = None,
    heights: Sequence[float] | None = None,
) -> dict:
    """Build a normalized row-based layout definition.

    ``columns`` gives the number of equal-width slots per row. ``heights``
    gives row height weights, for example percentages; values are normalized
    so they sum to 1.0. When omitted, rows share the page equally.

    Each row is laid out edge-to-edge: the first slot starts at x=0, every slot
    ends exactly where the next begins, and the last slot ends at x=1. Row
    heights follow the same edge-to-edge rule so consecutive rows touch. This
    is required for :class:`SlotAwareRenderer` to insert the spacing gutter;
    any positive normalized gap would instead be pasted over by the next slot.

    Raises:
        ValueError: If the key is empty, no rows are given, a row has no
            columns, or the height count does not match the row count.
    """
    if not key.strip():
        raise ValueError("layout key must be a non-empty string")
    if not columns:
        raise ValueError("at least one row is required")
    if any(count < 1 for count in columns):
        raise ValueError("every row needs at least one column")
    weights = normalize_weights(heights if heights is not None else [1.0] * len(columns))
    if len(weights) != len(columns):
        raise ValueError(f"got {len(columns)} rows but {len(weights)} row heights")

    y_edges = _height_edges(weights)
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
        "name": name or key.replace("_", " ").title(),
        "slots": slots,
    }


def yaml_text(data: dict) -> str:
    """Serialize a layout mapping to deterministic YAML text."""
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def write_yaml(path: Path, data: dict, *, dry_run: bool = False) -> bool:
    """Write a layout mapping, skipping unchanged files.

    Returns:
        ``True`` when the file was (or would be) written, ``False`` when the
        existing content already matches.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml_text(data)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return True


def write_builtin_templates(target_dir: Path, *, dry_run: bool = False) -> list[Path]:
    """Write the built-in row-based template YAML files.

    Existing files with the same key are replaced only when their content differs.
    Returns the list of written (or would-be-written) paths.
    """
    written: list[Path] = []
    for key, spec in BUILTIN_ROW_TEMPLATES.items():
        data = build_row_layout(
            key,
            spec.columns,
            name=spec.name,
            heights=spec.heights,
        )
        path = target_dir / f"{key}.yaml"
        if write_yaml(path, data, dry_run=dry_run):
            written.append(path)
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_geometry_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the page and spacing options shared by validate and generate."""
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


def _geometry(args: argparse.Namespace) -> tuple[int, int, int, int]:
    """Resolve page pixels, spacing pixels and the minimum gap from CLI args."""
    width_px, height_px = page_dimensions(args.width_mm, args.height_mm, args.dpi)
    spacing_px = round(args.spacing_mm / 25.4 * args.dpi)
    min_gap_px = args.min_gap_px
    if min_gap_px is None:
        min_gap_px = 1 if spacing_px > 0 else 0
    return width_px, height_px, spacing_px, min_gap_px


def _print_report(report: Report) -> tuple[int, int]:
    """Print all findings and return ``(errors, warnings)``."""
    errors = 0
    warnings = 0
    for issue in report.issues:
        prefix = "ERROR" if issue.severity == "error" else "WARN "
        location = f"{issue.layout}:{issue.slot}"
        print(f"{prefix} {location}: {issue.message}")
        if issue.severity == "error":
            errors += 1
        else:
            warnings += 1
    return errors, warnings


def _resolve_output(raw_output: str | None, key: str | None) -> Path | None:
    """Resolve the generate output target.

    ``None`` and ``-`` mean standard output. An existing directory is expanded
    to ``<key>.yaml`` inside it.
    """
    if raw_output is None or raw_output == "-":
        return None
    path = Path(raw_output)
    if path.is_dir():
        if not key:
            raise ValueError("--key is required when --output is a directory")
        return path / f"{key}.yaml"
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError(f"--output must end in .yaml or .yml: {raw_output}")
    return path


def _run_validate(args: argparse.Namespace) -> int:
    """Handle the ``validate`` subcommand."""
    width_px, height_px, spacing_px, min_gap_px = _geometry(args)
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
        report_errors, report_warnings = _print_report(report)
        errors += report_errors
        warnings += report_warnings

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


def _run_generate(args: argparse.Namespace) -> int:
    """Handle the ``generate`` subcommand."""
    try:
        columns = parse_columns(args.columns)
        heights = parse_heights(args.heights) if args.heights else None
        output = _resolve_output(args.output, args.key)
        key = args.key or (output.stem if output is not None else "")
        if not key:
            raise ValueError("--key is required when writing to stdout")
        data = build_row_layout(key, columns, name=args.name, heights=heights)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.check:
        width_px, height_px, spacing_px, min_gap_px = _geometry(args)
        report = validate_data(
            data,
            key=key,
            file_name=output.name if output is not None else None,
            page_width=width_px,
            page_height=height_px,
            spacing_px=spacing_px,
            min_gap_px=min_gap_px,
            neighbour_tol=args.neighbour_tol,
        )
        errors, warnings = _print_report(report)
        if errors:
            return 1
        print(f"OK {key}: {len(data['slots'])} slots, {warnings} warning(s)")

    text = yaml_text(data)
    if output is None:
        sys.stdout.write(text)
        return 0

    if write_yaml(output, data, dry_run=args.dry_run):
        prefix = "dry-run write" if args.dry_run else "write"
        print(f"{prefix} {output}")
    else:
        print(f"unchanged {output}")
    return 0


def _run_write_templates(args: argparse.Namespace) -> int:
    """Handle the ``write-templates`` subcommand."""
    written = write_builtin_templates(BUILTIN_LAYOUTS, dry_run=args.dry_run)
    prefix = "dry-run write" if args.dry_run else "write"
    for path in written:
        print(f"{prefix} {path.relative_to(ROOT)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Validate layout YAMLs and generate row-based templates.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate layout YAML files against renderer spacing geometry.",
    )
    validate_parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="YAML file or directory to validate. Repeatable. Defaults to built-in layouts.",
    )
    validate_parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when validation reports errors.",
    )
    _add_geometry_arguments(validate_parser)
    validate_parser.set_defaults(handler=_run_validate)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a row-based layout YAML file from column and height specifications.",
    )
    generate_parser.add_argument(
        "--columns",
        required=True,
        help="Comma-separated slot count per row, e.g. 4,3,5.",
    )
    generate_parser.add_argument(
        "--heights",
        help=(
            "Comma-separated row height weights (percentages), e.g. 30,40,30. "
            "Values are normalized to sum to 1.0; omit for equal heights."
        ),
    )
    generate_parser.add_argument(
        "--key",
        help="Layout key. Defaults to the output file stem.",
    )
    generate_parser.add_argument(
        "--name",
        help="Display name. Defaults to a title-cased key.",
    )
    generate_parser.add_argument(
        "--output",
        "-o",
        help="Output YAML file or existing directory. Defaults to stdout.",
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write the output file.",
    )
    generate_parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the generated layout and exit non-zero on errors.",
    )
    _add_geometry_arguments(generate_parser)
    generate_parser.set_defaults(handler=_run_generate)

    templates_parser = subparsers.add_parser(
        "write-templates",
        help="Write the built-in row-based template YAML files.",
    )
    templates_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be written.",
    )
    templates_parser.set_defaults(handler=_run_write_templates)

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
