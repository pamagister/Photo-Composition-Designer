"""Full-page composition from explicit project data.

The renderer combines the slot-based photo collage with the established
calendar strip, local map, description and title behaviour. It is independent
of SQLite and FastAPI: the application layer resolves photos and builds a
:class:`PageRenderInput` before calling :class:`PageComposer`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from PIL import Image, ImageChops

from photo_composition_designer.core.anniversaries import Anniversaries
from photo_composition_designer.core.color import Color
from photo_composition_designer.core.helpers import mm_to_px
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.layouts.loader import LayoutTemplate
from photo_composition_designer.render.calendar import CalendarRenderer
from photo_composition_designer.render.description import DescriptionRenderer
from photo_composition_designer.render.slot_renderer import SlotAwareRenderer, SlotPhoto

if TYPE_CHECKING:
    from photo_composition_designer.render.object_detector import ObjectDetector

MapRendererFactory = Callable[[list[tuple[float, float]]], Image.Image]


@dataclass(frozen=True)
class PageRenderInput:
    """Everything needed to render one calendar page."""

    page_date: date
    description: str
    layout: LayoutTemplate | None
    assigned_photos: Mapping[str, SlotPhoto | None] = field(default_factory=dict)
    output_profile: OutputProfile = field(default_factory=OutputProfile)
    gps_coordinates: tuple[tuple[float, float], ...] = ()
    title: str = ""
    title_page: bool = False
    anniversaries: Anniversaries | None = None


class PageComposer:
    """Compose a complete page image from a :class:`PageRenderInput`."""

    def __init__(
        self,
        *,
        object_detector: ObjectDetector | None = None,
        map_renderer: MapRendererFactory | None = None,
    ) -> None:
        self._object_detector = object_detector
        self._map_renderer = map_renderer

    def render(self, page: PageRenderInput) -> Image.Image:
        """Render the page and return an RGB image."""
        profile = page.output_profile
        settings = profile.to_settings()
        dpi = profile.size.dpi
        page_width, page_height = profile.page_size_px()
        background = Color.from_hex(profile.style.background_color).to_pil()

        canvas = Image.new("RGB", (page_width, page_height), background)

        margin_sides = mm_to_px(profile.layout.margin_sides, dpi)
        margin_top = mm_to_px(profile.layout.margin_top, dpi)
        margin_bottom = mm_to_px(profile.layout.margin_bottom, dpi)
        spacing = mm_to_px(profile.layout.spacing, dpi)

        calendar_height = mm_to_px(profile.size.calendar_height, dpi)
        show_calendar = calendar_height > 0 and profile.calendar.use_calendar
        content_top = margin_top

        description_image: Image.Image | None = None
        if profile.layout.use_photo_description:
            description_image = DescriptionRenderer(
                width_px=page_width,
                font=profile.style.font_description.to_font(),
                spacing_px=spacing,
                margin_side_px=margin_sides,
                background_color=background,
                dpi=dpi,
            ).generate(page.description)

        calendar_strip = (
            self._render_calendar_strip(page, profile, settings, page_width)
            if show_calendar
            else None
        )
        calendar_ink_top = 0
        if calendar_strip is not None and description_image is not None:
            difference = ImageChops.difference(
                calendar_strip, Image.new("RGB", calendar_strip.size, background)
            )
            bounds = difference.getbbox()
            calendar_ink_top = bounds[1] if bounds is not None else 0

        description_ink_bottom = 0
        if description_image is not None:
            bounds = description_image.getbbox()
            description_ink_bottom = bounds[3] if bounds is not None else description_image.height

        content_left = margin_sides
        content_width = max(1, page_width - 2 * margin_sides)
        content_bottom = page_height - margin_bottom
        calendar_top = content_bottom - calendar_height if show_calendar else content_bottom

        if description_image is not None:
            description_bottom = (
                calendar_top + calendar_ink_top if show_calendar else content_bottom
            )
            description_top = description_bottom - description_ink_bottom
            photo_bottom = description_top
        else:
            description_top = None
            photo_bottom = calendar_top - spacing if show_calendar else content_bottom
        content_height = max(1, photo_bottom - content_top)

        map_image = self._render_map(page, profile, content_width, content_height, spacing)
        slots_width = content_width
        if map_image is not None:
            slots_width = max(1, content_width - map_image.width - spacing)

        if page.layout is not None:
            collage = SlotAwareRenderer(settings, object_detector=self._object_detector).render(
                page.layout,
                dict(page.assigned_photos),
                page_width=slots_width,
                page_height=content_height,
                background_color=background,
            )
            canvas.paste(collage, (content_left, content_top))

        if map_image is not None:
            map_x = content_left + slots_width + spacing
            canvas.paste(map_image, (map_x, content_top))

        if calendar_strip is not None:
            canvas.paste(calendar_strip, (0, calendar_top))

        if description_image is not None and description_top is not None:
            canvas.paste(
                description_image,
                (0, description_top),
                description_image,
            )

        return canvas

    def _render_calendar_strip(
        self,
        page: PageRenderInput,
        profile: OutputProfile,
        settings,
        page_width: int,
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
        if page.title_page and page.title:
            return renderer.generateTitle(page.title, page_width, calendar_height)
        return renderer.generate(
            datetime.combine(page.page_date, time.min), page_width, calendar_height
        )

    def _render_map(
        self,
        page: PageRenderInput,
        profile: OutputProfile,
        content_width: int,
        content_height: int,
        spacing: int,
    ) -> Image.Image | None:
        if not profile.geo.use_photo_location_maps or not page.gps_coordinates:
            return None
        map_width = mm_to_px(profile.geo.map_width, profile.size.dpi)
        map_height = mm_to_px(profile.geo.map_height, profile.size.dpi)
        if map_height > content_height or map_width + spacing >= content_width:
            return None
        renderer = self._map_renderer or self._default_map_renderer(profile)
        return renderer(list(page.gps_coordinates))

    @staticmethod
    def _default_map_renderer(profile: OutputProfile) -> MapRendererFactory:
        from photo_composition_designer.render.map import MapRenderer

        renderer = MapRenderer(
            mapHeight=mm_to_px(profile.geo.map_height, profile.size.dpi),
            mapWidth=mm_to_px(profile.geo.map_width, profile.size.dpi),
            minimalExtension=profile.geo.minimal_extension,
            backgroundColor=Color.from_hex(profile.style.background_color).to_pil(),
            textColor1=profile.style.font_large.to_font().color.to_pil(),
        )
        return renderer.generate


__all__ = ["MapRendererFactory", "PageComposer", "PageRenderInput"]
