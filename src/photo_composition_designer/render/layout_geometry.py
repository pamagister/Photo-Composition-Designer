"""Shared collage geometry for the renderer and the editor overlay.

The rendered collage sits inside a content box (margins, calendar strip,
description and optional map). Slot coordinates are normalised to that box, not
to the page. The editor overlay must use the same box or its dropzones will not
line up with the rendered photos.

Both the renderer (:class:`~photo_composition_designer.render.page.PageComposer`)
and the GUI context builders derive the box from :func:`compute_collage_box` so
the two can never drift apart.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import TYPE_CHECKING

from PIL import Image, ImageChops

from photo_composition_designer.core.color import Color
from photo_composition_designer.core.helpers import mm_to_px
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.render.calendar import CalendarRenderer
from photo_composition_designer.render.description import DescriptionRenderer

if TYPE_CHECKING:
    from photo_composition_designer.render.page import PageRenderInput

MapRendererFactory = Callable[[list[tuple[float, float]]], Image.Image]

#: Maximum number of cached map renders. Each entry is a PIL Image that
#: can be large (e.g., 236x213 at 300 dpi), so the cap is conservative.
_MAP_CACHE_SIZE = 16

#: Bounded LRU cache for map renders. Key: (profile_hash, map_width,
#: map_height, sorted(gps_coordinates)). Value: PIL Image.
_map_cache: OrderedDict[tuple, Image.Image] = OrderedDict()


def clear_map_cache() -> None:
    """Clear the map render cache. Intended for tests and benchmarks."""
    _map_cache.clear()


def _map_cache_key(
    profile: OutputProfile,
    map_width: int,
    map_height: int,
    gps_coordinates: list[tuple[float, float]],
) -> tuple:
    """Return a cache key for a map render.

    The key includes the profile hash (so a style or DPI change invalidates
    the cache), the map dimensions, and the sorted coordinates (so a
    coordinate change produces a new key and order does not matter).
    """
    return (
        profile.profile_hash(),
        map_width,
        map_height,
        tuple(sorted(gps_coordinates)),
    )


@dataclass(frozen=True)
class CollageBox:
    """Absolute pixel geometry of the collage content box within a page."""

    page_width: int
    page_height: int
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class PreparedCollage:
    """Rendered sub-images and the content box shared by the page composer."""

    box: CollageBox
    background: Image.Image
    description_image: Image.Image | None
    description_top: int | None
    map_image: Image.Image | None
    map_x: int
    calendar_strip: Image.Image | None
    calendar_top: int


def _map_dimensions(profile: OutputProfile, calendar_height: int) -> tuple[int, int]:
    """Return the map width and height for the calendar orientation."""
    map_size = mm_to_px(profile.geo.map_size, profile.size.dpi)
    if profile.calendar.horizontal_orientation:
        return map_size, calendar_height
    # A vertical calendar is a tall strip; its width is the calendar's
    # cross-axis size, so the map matches that width and uses map_size as
    # its height.
    return calendar_height, map_size


def _render_map(
    page: PageRenderInput,
    profile: OutputProfile,
    map_width: int,
    map_height: int,
    map_renderer: MapRendererFactory | None,
) -> Image.Image | None:
    # Custom renderers (e.g., test doubles) bypass the cache so tests
    # that inject a fake renderer see exactly the expected output.
    if map_renderer is not None:
        return map_renderer(list(page.gps_coordinates))
    if not page.gps_coordinates:
        return None
    key = _map_cache_key(profile, map_width, map_height, list(page.gps_coordinates))
    cached = _map_cache.get(key)
    if cached is not None:
        _map_cache.move_to_end(key)
        return cached
    renderer = _default_map_renderer(profile, map_width, map_height)
    image = renderer(list(page.gps_coordinates))
    if image is not None:
        _map_cache[key] = image
        _map_cache.move_to_end(key)
        if len(_map_cache) > _MAP_CACHE_SIZE:
            _map_cache.popitem(last=False)
    return image


def _default_map_renderer(
    profile: OutputProfile,
    map_width: int,
    map_height: int,
) -> MapRendererFactory:
    from photo_composition_designer.render.map import MapRenderer

    renderer = MapRenderer(
        mapHeight=map_height,
        mapWidth=map_width,
        minimalExtension=profile.geo.minimal_extension,
        backgroundColor=Color.from_hex(profile.style.background_color).to_pil(),
        textColor1=profile.style.font_large.to_font().color.to_pil(),
    )
    return renderer.generate


def _strip_ink_top(strip: Image.Image, background: tuple[int, ...]) -> int:
    """Return the y coordinate of the first non-background row in a strip."""
    difference = ImageChops.difference(strip, Image.new("RGB", strip.size, background))
    bounds = difference.getbbox()
    return bounds[1] if bounds is not None else 0


def _render_calendar_strip(
    page: PageRenderInput,
    profile: OutputProfile,
    settings,
    width: int,
    *,
    force_calendar: bool = False,
) -> Image.Image:
    calendar_height = mm_to_px(profile.size.calendar_height, profile.size.dpi)
    margin_sides = mm_to_px(profile.layout.margin_sides, profile.size.dpi)
    renderer = CalendarRenderer(
        backgroundColor=Color.from_hex(profile.style.background_color).to_pil(),
        fontLarge=settings.style.fontLarge.value,
        fontSmall=settings.style.fontSmall.value,
        fontHoliday=settings.style.fontAnniversaries.value,
        language=profile.calendar.language,
        startDate=datetime.combine(page.page_date, time.min),
        holidayCountries=list(profile.calendar.holiday_countries),
        useShortDayNames=profile.calendar.use_short_day_names,
        useShortMonthNames=profile.calendar.use_short_month_names,
        marginSides=margin_sides,
        anniversaries=page.anniversaries,
        dpi=profile.size.dpi,
        horizontal=profile.calendar.horizontal_orientation,
    )
    if page.title_page and page.title and not force_calendar:
        return renderer.generateTitle(page.title, width, calendar_height)
    return renderer.generate(datetime.combine(page.page_date, time.min), width, calendar_height)


def prepare_collage(
    page: PageRenderInput,
    profile: OutputProfile,
    *,
    map_renderer: MapRendererFactory | None = None,
) -> PreparedCollage:
    """Render the page's sub-images and compute the collage content box.

    This mirrors the geometry half of ``PageComposer.render`` exactly. The
    composer consumes the returned sub-images for pasting; callers that only
    need geometry (the editor overlay) use :func:`compute_collage_box`.
    """
    settings = profile.to_settings()
    dpi = profile.size.dpi
    page_width, page_height = profile.page_size_px()
    background = Color.from_hex(profile.style.background_color).to_pil()

    margin_sides = mm_to_px(profile.layout.margin_sides, dpi)
    margin_top = mm_to_px(profile.layout.margin_top, dpi)
    margin_bottom = mm_to_px(profile.layout.margin_bottom, dpi)
    spacing = mm_to_px(profile.layout.spacing, dpi)

    calendar_height = mm_to_px(profile.size.calendar_height, dpi)
    title_page = page.title_page and bool(page.title)
    show_calendar = (
        calendar_height > 0
        and profile.calendar.use_calendar
        and not page.hide_calendar_strip
        and not title_page
    )
    has_bottom_strip = title_page or show_calendar
    show_description = profile.layout.use_photo_description and not page.hide_description
    content_top = margin_top

    description_image: Image.Image | None = None
    if show_description:
        description_image = DescriptionRenderer(
            width_px=page_width,
            font=profile.style.font_description.to_font(),
            spacing_px=spacing,
            margin_side_px=margin_sides,
            background_color=background,
            dpi=dpi,
        ).generate(page.description)

    map_image: Image.Image | None = None
    map_x = 0
    calendar_width = page_width
    if has_bottom_strip:
        map_width, map_height = _map_dimensions(profile, calendar_height)
        map_x = page_width - margin_sides - map_width
        min_calendar_width = 2 * margin_sides + spacing
        if (
            not page.hide_local_map
            and profile.geo.use_photo_location_maps
            and map_width > 0
            and map_height > 0
            and map_x >= min_calendar_width
        ):
            map_image = _render_map(page, profile, map_width, map_height, map_renderer)
            if map_image is not None:
                calendar_width = map_x

    calendar_strip = (
        _render_calendar_strip(page, profile, settings, calendar_width)
        if has_bottom_strip
        else None
    )
    calendar_ink_top = 0
    if calendar_strip is not None and description_image is not None:
        # A title page replaces the calendar with the composition title, whose
        # first ink sits lower than a calendar's day names. Measure a real
        # calendar strip instead so the description keeps the same distance from
        # the page bottom as on pages with a calendar.
        ink_strip = calendar_strip
        if title_page and map_image is None:
            ink_strip = _render_calendar_strip(
                page, profile, settings, calendar_width, force_calendar=True
            )
        calendar_ink_top = _strip_ink_top(ink_strip, background)

    description_ink_bottom = 0
    if description_image is not None:
        bounds = description_image.getbbox()
        description_ink_bottom = bounds[3] if bounds is not None else description_image.height

    content_left = margin_sides
    content_width = max(1, page_width - 2 * margin_sides)
    content_bottom = page_height - margin_bottom
    calendar_top = content_bottom - calendar_height if has_bottom_strip else content_bottom

    if description_image is not None:
        if has_bottom_strip:
            # With a map in the bottom-right corner the description must end
            # above it instead of using the calendar's blank upper margin.
            description_bottom = calendar_top + (0 if map_image is not None else calendar_ink_top)
        else:
            description_bottom = content_bottom
        description_top = description_bottom - description_ink_bottom
        photo_bottom = description_top
    else:
        description_top = None
        photo_bottom = calendar_top - spacing if has_bottom_strip else content_bottom
    content_height = max(1, photo_bottom - content_top)

    box = CollageBox(
        page_width=page_width,
        page_height=page_height,
        left=content_left,
        top=content_top,
        width=content_width,
        height=content_height,
    )
    return PreparedCollage(
        box=box,
        background=background,
        description_image=description_image,
        description_top=description_top,
        map_image=map_image,
        map_x=map_x,
        calendar_strip=calendar_strip,
        calendar_top=calendar_top,
    )


def compute_collage_box(
    page: PageRenderInput,
    profile: OutputProfile | None = None,
    *,
    map_renderer: MapRendererFactory | None = None,
) -> CollageBox:
    """Return the collage content box for a page without rendering the collage.

    The optional ``map_renderer`` only affects whether a map is considered
    present (and therefore the description position); pass a lightweight stub
    when the caller does not need the real map image.
    """
    effective_profile = profile or page.output_profile
    return prepare_collage(page, effective_profile, map_renderer=map_renderer).box


@dataclass(frozen=True)
class SlotOverlayRect:
    """One slot rectangle expressed as percentages of the full page."""

    slot_id: int
    slot_key: str
    left: float
    top: float
    width: float
    height: float


def slot_overlay_rectangles(
    slots,
    box: CollageBox,
) -> list[SlotOverlayRect]:
    """Convert normalised slots into page-percentage overlay rectangles.

    ``slots`` are objects exposing ``id``, ``slot_key``, ``x``, ``y``, ``width``
    and ``height`` (for example persisted ``LayoutSlot`` rows). The returned
    percentages are relative to the full page so they can position absolutely
    positioned dropzones over the preview image.
    """
    rectangles: list[SlotOverlayRect] = []
    for slot in slots:
        left = (box.left + slot.x * box.width) / box.page_width * 100.0
        top = (box.top + slot.y * box.height) / box.page_height * 100.0
        width = slot.width * box.width / box.page_width * 100.0
        height = slot.height * box.height / box.page_height * 100.0
        rectangles.append(
            SlotOverlayRect(
                slot_id=slot.id,
                slot_key=slot.slot_key,
                left=left,
                top=top,
                width=width,
                height=height,
            )
        )
    return rectangles


__all__ = [
    "CollageBox",
    "MapRendererFactory",
    "PreparedCollage",
    "SlotOverlayRect",
    "clear_map_cache",
    "compute_collage_box",
    "prepare_collage",
    "slot_overlay_rectangles",
]
