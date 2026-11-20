"""Full-page composition from explicit project data.

The renderer combines the slot-based photo collage with the established
calendar strip, local map, description and title behaviour. It is independent
of SQLite and FastAPI: the application layer resolves photos and builds a
:class:`PageRenderInput` before calling :class:`PageComposer`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from photo_composition_designer.core.anniversaries import Anniversaries
from photo_composition_designer.core.helpers import mm_to_px
from photo_composition_designer.core.output_profile import OutputProfile
from photo_composition_designer.layouts.loader import LayoutTemplate
from photo_composition_designer.render.layout_geometry import (
    MapRendererFactory,
    prepare_collage,
)
from photo_composition_designer.render.slot_renderer import SlotAwareRenderer, SlotPhoto

if TYPE_CHECKING:
    from photo_composition_designer.render.object_detector import ObjectDetector


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
    hide_local_map: bool = False
    hide_calendar_strip: bool = False
    hide_description: bool = False
    center_description: bool | None = None
    anniversaries: Anniversaries | None = None


def _paste_rounded(
    canvas: Image.Image,
    image: Image.Image,
    position: tuple[int, int],
    radius: int,
) -> None:
    """Paste an image with rounded corners using the given radius."""
    if radius <= 0:
        canvas.paste(image, position)
        return
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, image.width - 1, image.height - 1),
        radius=radius,
        fill=255,
    )
    canvas.paste(image, position, mask)


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
        prepared = prepare_collage(page, profile, map_renderer=self._map_renderer)
        box = prepared.box

        canvas = Image.new("RGB", (box.page_width, box.page_height), prepared.background)

        if page.layout is not None:
            collage = SlotAwareRenderer(settings, object_detector=self._object_detector).render(
                page.layout,
                dict(page.assigned_photos),
                page_width=box.width,
                page_height=box.height,
                background_color=prepared.background,
            )
            canvas.paste(collage, (box.left, box.top))

        if prepared.map_image is not None:
            spacing = mm_to_px(settings.layout.spacing.value, settings.size.dpi.value)
            radius = 0
            if settings.layout.useRoundedCorners.value and spacing > 0:
                radius = min(
                    spacing,
                    prepared.map_image.width // 2,
                    prepared.map_image.height // 2,
                )
            _paste_rounded(
                canvas,
                prepared.map_image,
                (prepared.map_x, prepared.map_top),
                radius,
            )

        if prepared.calendar_strip is not None:
            canvas.paste(prepared.calendar_strip, (0, prepared.calendar_top))

        if prepared.description_image is not None and prepared.description_top is not None:
            canvas.paste(
                prepared.description_image,
                (0, prepared.description_top),
                prepared.description_image,
            )

        return canvas


__all__ = ["MapRendererFactory", "PageComposer", "PageRenderInput"]
