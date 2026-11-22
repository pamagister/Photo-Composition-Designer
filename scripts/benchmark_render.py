"""Canonical, repeatable render-performance benchmark.

This is the single benchmark command referenced by
``docs/plans/2026-11-19-performance-many-photos.md``. It supersedes the ad-hoc
scripts that were used to establish the original baseline and consolidates
their measurements into one documented command. The shared seeding helpers live
in ``scripts/harness_common.py`` (kept out of ``src/`` and ``tests/``). It covers:

* full page render and preview-write time across 4/14/30/45 slots,
* two representative layout geometries (a single row and a multi-row grid),
* cold vs. warm preview at 200 and 800 px,
* GPS/map on and off,
* the project-wide "refresh all previews" bulk action,
* editor context and template render cost for many slots.

Run from the repository root:

    uv run python scripts/benchmark_render.py

The script builds a throwaway project from real JPEG fixtures in ``images/`` so
decode, EXIF and resize costs are representative. It never touches a real
workspace. Timings vary by machine; treat the output as a relative baseline,
not an acceptance gate.

Browser click-to-visible-preview latency is a separate, manual verification and
is not part of this component benchmark.
"""

from __future__ import annotations

import argparse
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

# Repository root and the sibling benchmark helpers live next to each other.
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from harness_common import cleanup, new_workspace, seed_project  # noqa: E402

from photo_composition_designer.core.output_profile import OutputProfile  # noqa: E402
from photo_composition_designer.project.rendering import (  # noqa: E402
    ProjectRenderingService,
    write_preview,
)
from photo_composition_designer.project.repositories import PageRepository  # noqa: E402

#: Slot counts exercised by the component benchmark.
SLOT_COUNTS = (4, 14, 30, 45)

#: Preview widths exercised for cold/warm measurements.
PREVIEW_WIDTHS = (200, 800)

#: Number of pages in the bulk "refresh all previews" workload.
BULK_PAGES = 10


@dataclass(frozen=True)
class Geometry:
    """A representative page geometry: one row vs. a multi-row grid."""

    key: str
    columns: int


#: A single row of full-height slots and a grid that wraps into multiple rows.
GEOMETRIES = (
    Geometry(key="row", columns=0),
    Geometry(key="grid", columns=6),
)


def _ms(start: float) -> float:
    """Return elapsed milliseconds since ``start``."""
    return (time.perf_counter() - start) * 1000


def _seed_grid(
    database,
    tmp: Path,
    *,
    slots: int,
    gps_count: int,
    columns: int,
):
    """Seed a project whose page uses a wrapped grid layout.

    ``harness_common.seed_project`` produces a single row of full-height slots.
    This variant wraps the same number of slots into ``columns`` columns so the
    benchmark covers a second, more square geometry with shorter slot edges.
    """
    from datetime import datetime as _datetime

    from photo_composition_designer.project.inventory import InventoryService
    from photo_composition_designer.project.models import LayoutSlot
    from photo_composition_designer.project.repositories import (
        AssignmentRepository,
        LayoutRepository,
        PhotoRepository,
    )
    from photo_composition_designer.project.services import ProjectService

    service = ProjectService(database)
    project = service.create_project(
        name="perf",
        page_count=1,
        start_date=_datetime(2027, 1, 4),
        output_profile={"size": {"width": 216, "height": 154, "dpi": 300}},
    )

    source = tmp / "source"
    source.mkdir(parents=True, exist_ok=True)
    files = sorted((REPO_ROOT / "images").glob("*.jpg"))
    for index in range(min(len(files), slots)):
        with Image.open(files[index]) as image:
            image.convert("RGB").save(source / f"photo_{index:03d}.jpg", quality=88)

    inventory = InventoryService(database)
    root = inventory.add_source_root(project.id, source)
    inventory.scan(project.id, source_root_id=root.id)

    if gps_count:
        connection = database.connect()
        photos = PhotoRepository(connection).list(project.id)
        for index, photo in enumerate(photos[:gps_count]):
            connection.execute(
                "UPDATE photos SET gps_lat = ?, gps_lon = ? WHERE id = ?",
                (51.05 + index * 0.01, 13.74 + index * 0.01, photo.id),
            )
        connection.commit()

    rows = max(1, (slots + columns - 1) // columns)
    with database.transaction() as connection:
        layouts = LayoutRepository(connection)
        pages = PageRepository(connection)
        assignments = AssignmentRepository(connection)
        photo_ids = [photo.id for photo in PhotoRepository(connection).list(project.id)]
        page = pages.list(project.id)[0]
        grid_slots = [
            LayoutSlot(
                id=0,
                layout_id=0,
                slot_key=f"slot_{index}",
                position=index,
                x=(index % columns) / columns,
                y=(index // columns) / rows,
                width=1.0 / columns,
                height=1.0 / rows,
                z_index=0,
                crop_mode="cover",
            )
            for index in range(slots)
        ]
        layout = layouts.add("perf_grid", 1, "PerfGrid", grid_slots)
        pages.set_layout(page.id, layout.id, layout.version)
        for index, slot in enumerate(layout.slots):
            assignments.assign(
                project_id=project.id,
                page_id=page.id,
                slot_id=slot.id,
                photo_id=photo_ids[index % len(photo_ids)],
            )
    return project.id, [page.id]


def _prepare(database, tmp: Path, *, slots: int, geometry: Geometry, gps_count: int):
    """Seed a project for one benchmark case and return (project_id, page_ids)."""
    if geometry.key == "grid":
        project_id, page_ids = _seed_grid(
            database,
            tmp,
            slots=slots,
            gps_count=gps_count,
            columns=geometry.columns,
        )
    else:
        project_id, page_ids = seed_project(database, tmp, slots=slots, gps_count=gps_count)
    if gps_count:
        _show_local_map(database, page_ids[0])
    return project_id, page_ids


def _show_local_map(database, page_id: int) -> None:
    """Clear the page's ``hide_local_map`` override so the map path renders.

    New projects start on a title page, which the schema hides the map on. The
    GPS benchmark case exists to exercise the (expensive) matplotlib map render,
    so it must opt that page back into the map.
    """
    from photo_composition_designer.project.repositories import PageRepository

    with database.transaction() as connection:
        PageRepository(connection).set_local_overrides(
            page_id,
            hide_local_map=False,
            hide_calendar_strip=False,
            hide_description=False,
        )


def measure_render(slots: int, geometry: Geometry, gps_count: int) -> dict[str, float]:
    """Measure full render time and preview-write time for one case."""
    tmp, database = new_workspace()
    try:
        project_id, page_ids = _prepare(
            database, tmp, slots=slots, geometry=geometry, gps_count=gps_count
        )
        rendering = ProjectRenderingService(database, preview_dir=tmp / "cache" / "previews")
        connection = database.connect()
        page = PageRepository(connection).get(page_ids[0])
        assert page is not None

        rendering.render_page_image(connection, page)  # warm imports / font caches

        start = time.perf_counter()
        for _ in range(3):
            rendering.render_page_image(connection, page)
        render_ms = _ms(start) / 3

        image = rendering.render_page_image(connection, page)
        writes: dict[int, float] = {}
        for width in PREVIEW_WIDTHS:
            start = time.perf_counter()
            write_preview(image, tmp / "cache" / f"preview_{width}.jpg", max_width=width)
            writes[width] = _ms(start)

        return {
            "render_ms": render_ms,
            "write200_ms": writes[200],
            "write800_ms": writes[800],
        }
    finally:
        database.close()
        cleanup(tmp)


def measure_preview(slots: int, geometry: Geometry) -> dict[str, float]:
    """Measure cold vs. warm preview time at each preview width."""
    tmp, database = new_workspace()
    try:
        project_id, page_ids = _prepare(database, tmp, slots=slots, geometry=geometry, gps_count=0)
        preview_dir = tmp / "cache" / "previews"
        rendering = ProjectRenderingService(database, preview_dir=preview_dir)
        connection = database.connect()
        page = PageRepository(connection).get(page_ids[0])
        assert page is not None
        rendering.render_page_image(connection, page)  # warm page render path

        result: dict[str, float] = {}
        for width in PREVIEW_WIDTHS:
            target = rendering.render_preview(project_id, page_ids[0], max_width=width)
            target.unlink(missing_ok=True)  # force a cold render

            start = time.perf_counter()
            rendering.render_preview(project_id, page_ids[0], max_width=width)
            result[f"cold{width}_ms"] = _ms(start)

            start = time.perf_counter()
            rendering.render_preview(project_id, page_ids[0], max_width=width)
            result[f"warm{width}_ms"] = _ms(start)

        return result
    finally:
        database.close()
        cleanup(tmp)


def measure_bulk(slots: int) -> dict[str, float]:
    """Measure the project-wide "refresh all previews" bulk action."""
    tmp, database = new_workspace()
    try:
        project_id, page_ids = seed_project(database, tmp, slots=slots, page_count=BULK_PAGES)
        preview_dir = tmp / "cache" / "previews"
        rendering = ProjectRenderingService(database, preview_dir=preview_dir)

        for cached in preview_dir.glob("pages/*.jpg"):
            cached.unlink()
        start = time.perf_counter()
        for page_id in page_ids:
            rendering.render_preview(project_id, page_id, max_width=200)
        cold_s = time.perf_counter() - start

        start = time.perf_counter()
        for page_id in page_ids:
            rendering.render_preview(project_id, page_id, max_width=200)
        warm_s = time.perf_counter() - start

        return {"bulk_cold_s": cold_s, "bulk_warm_s": warm_s}
    finally:
        database.close()
        cleanup(tmp)


def measure_fragment(slots: int) -> dict[str, float]:
    """Measure editor context build and template render cost."""
    from photo_composition_designer.gui.routes.projects import _page_context
    from photo_composition_designer.gui.templating import TEMPLATES

    tmp, database = new_workspace()
    try:
        project_id, page_ids = seed_project(database, tmp, slots=slots, page_count=1)
        page_id = page_ids[0]

        for _ in range(2):
            _page_context(database, project_id, page_id)
        start = time.perf_counter()
        for _ in range(10):
            _page_context(database, project_id, page_id)
        context_ms = _ms(start) / 10

        context = _page_context(database, project_id, page_id)
        assert context is not None
        start = time.perf_counter()
        for _ in range(10):
            TEMPLATES.get_template("partials/editor_canvas.html").render(**context)
        canvas_ms = _ms(start) / 10

        return {"context_ms": context_ms, "canvas_ms": canvas_ms}
    finally:
        database.close()
        cleanup(tmp)


def _environment() -> dict[str, str]:
    """Return run metadata so results are reproducible."""
    try:
        import numpy
        import PIL

        versions = (
            f"Python {platform.python_version()}, "
            f"Pillow {PIL.__version__}, numpy {numpy.__version__}"
        )
    except Exception:  # pragma: no cover - metadata only
        versions = f"Python {platform.python_version()}"
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "versions": versions,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "page_profile": str(OutputProfile.default().page_size_px()) + " @ 300 dpi",
    }


def _print_environment() -> None:
    """Print a compact environment header above the result tables."""
    print("=== Environment ===")
    for key, value in _environment().items():
        print(f"{key:>10}: {value}")
    print()


def _print_render_table(rows: list[tuple[str, dict[str, float]]]) -> None:
    print("=== Full page render + preview write ===")
    print(f"{'case':>12} {'render':>9} {'write200':>9} {'write800':>9}   (ms)")
    for label, row in rows:
        print(
            f"{label:>12} {row['render_ms']:9.0f} "
            f"{row['write200_ms']:9.0f} {row['write800_ms']:9.0f}"
        )
    print()


def _print_preview_table(rows: list[tuple[str, dict[str, float]]]) -> None:
    print("=== Preview cold vs. warm ===")
    print(f"{'case':>12} {'cold200':>9} {'warm200':>9} {'cold800':>9} {'warm800':>9}   (ms)")
    for label, row in rows:
        print(
            f"{label:>12} {row['cold200_ms']:9.0f} {row['warm200_ms']:9.2f} "
            f"{row['cold800_ms']:9.0f} {row['warm800_ms']:9.2f}"
        )
    print()


def _print_bulk_table(rows: list[tuple[int, dict[str, float]]]) -> None:
    print(f"=== Bulk refresh all previews ({BULK_PAGES} pages, 200 px) ===")
    print(f"{'slots':>6} {'cold':>9} {'warm':>9}   (s)")
    for slots, row in rows:
        print(f"{slots:>6} {row['bulk_cold_s']:9.2f} {row['bulk_warm_s']:9.3f}")
    print()


def _print_fragment_table(rows: list[tuple[int, dict[str, float]]]) -> None:
    print("=== Editor context + canvas template (45 slots) ===")
    print(f"{'slots':>6} {'context':>9} {'canvas':>9}   (ms)")
    for slots, row in rows:
        print(f"{slots:>6} {row['context_ms']:9.1f} {row['canvas_ms']:9.1f}")
    print()


def run(gps: bool = False, geometries: tuple[Geometry, ...] = GEOMETRIES) -> None:
    """Run the full benchmark and print the result tables."""
    _print_environment()

    render_rows: list[tuple[str, dict[str, float]]] = []
    preview_rows: list[tuple[str, dict[str, float]]] = []
    for geometry in geometries:
        for slots in SLOT_COUNTS:
            gps_count = 4 if gps else 0
            label = f"{slots:02d}-{geometry.key}"
            render_rows.append((label, measure_render(slots, geometry, gps_count=gps_count)))
            preview_rows.append((label, measure_preview(slots, geometry)))
    _print_render_table(render_rows)
    _print_preview_table(preview_rows)

    bulk_rows = [(slots, measure_bulk(slots)) for slots in (14, 30)]
    _print_bulk_table(bulk_rows)

    fragment_rows = [(45, measure_fragment(45))]
    _print_fragment_table(fragment_rows)


def main() -> None:
    """Parse arguments and run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--gps",
        action="store_true",
        help="Seed GPS coordinates on some photos to exercise the map path.",
    )
    parser.add_argument(
        "--geometry",
        choices=("row", "grid", "both"),
        default="both",
        help="Which layout geometry/ies to measure (default: both).",
    )
    args = parser.parse_args()

    geometries = {
        "row": (Geometry(key="row", columns=0),),
        "grid": (Geometry(key="grid", columns=6),),
        "both": GEOMETRIES,
    }[args.geometry]

    run(gps=args.gps, geometries=geometries)


if __name__ == "__main__":
    main()
