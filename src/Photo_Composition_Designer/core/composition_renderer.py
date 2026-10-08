"""Render page-level photo compositions from injected image renderers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from logging import Logger

from PIL import Image, ImageDraw

from Photo_Composition_Designer.common.Photo import Photo, get_photo_dates
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.composition_layout import CompositionLayout
from Photo_Composition_Designer.image.CalendarRenderer import CalendarRenderer
from Photo_Composition_Designer.image.CollageRenderer import CollageRenderer
from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer
from Photo_Composition_Designer.image.MapRenderer import MapRenderer


@dataclass(frozen=True)
class CompositionRenderContext:
    """Dependencies required to render a complete composition page."""

    config: ConfigParameterManager
    logger: Logger
    layout: CompositionLayout
    calendar_renderer: CalendarRenderer
    collage_renderer: CollageRenderer
    description_renderer: DescriptionRenderer
    map_renderer: MapRenderer


class CompositionPageRenderer:
    """Compose the collage, calendar, map, and description on a page."""

    def __init__(self, context: CompositionRenderContext) -> None:
        """Initialize the page renderer with its rendering dependencies."""
        self.context = context

    def render(
        self,
        photos: list[Photo],
        composition_date: datetime,
        photo_description: str = "",
        is_title: bool = False,
    ) -> Image.Image:
        """Render one full page containing the supplied photos and metadata."""
        context = self.context
        config = context.config
        layout = context.layout
        calendar_renderer = context.calendar_renderer
        collage_renderer = context.collage_renderer
        description_renderer = context.description_renderer
        map_renderer = context.map_renderer

        background_color = config.style.backgroundColor.value.to_pil()
        text_color = config.style.fontSmall.value.color.to_pil()
        composition = Image.new(
            "RGBA", (layout.width_px, layout.height_px), (*background_color, 255)
        )
        (
            processed_description,
            no_calendar_flag,
            no_description_flag,
        ) = layout.process_photo_description(photo_description)
        collage_renderer.height = layout.get_available_collage_height_px(
            no_calendar_flag, no_description_flag
        )
        collage_renderer.width = layout.get_available_collage_width_px()

        calendar_x, calendar_y = 0, 0
        calendar_width, calendar_height = 0, 0
        map_x, map_y = 0, 0

        if is_title and layout.composition_title:
            calendar_width = layout.calendar_secondary_dim_px
            calendar_height = layout.calendar_primary_dim_px
            calendar_x = layout.margin_sides_px
            calendar_y = layout.height_px - layout.calendar_primary_dim_px - layout.margin_bottom_px
            title_image = calendar_renderer.generateTitle(
                layout.composition_title, calendar_width, calendar_height
            )
            composition.paste(title_image, (calendar_x, calendar_y))
        elif config.calendar.useCalendar.value and not no_calendar_flag:
            if layout.horizontal_orientation:
                calendar_width = layout.calendar_secondary_dim_px
                calendar_height = layout.calendar_primary_dim_px
                calendar_x = layout.margin_sides_px
                calendar_y = (
                    layout.height_px - layout.calendar_primary_dim_px - layout.margin_bottom_px
                )
                if config.geo.usePhotoLocationMaps.value:
                    calendar_width -= map_renderer.width + layout.spacing_px
            else:
                calendar_width = layout.calendar_primary_dim_px
                calendar_height = layout.calendar_secondary_dim_px
                calendar_x = layout.margin_sides_px
                calendar_y = layout.margin_top_px
                if config.geo.usePhotoLocationMaps.value:
                    calendar_height -= map_renderer.height + layout.spacing_px

            calendar_image = calendar_renderer.generate(
                composition_date, calendar_width, calendar_height
            )
            composition.paste(calendar_image, (calendar_x, calendar_y))

        if config.geo.usePhotoLocationMaps.value and not is_title and not no_calendar_flag:
            coordinates = [
                location for photo in photos if (location := photo.get_location()) is not None
            ]
            map_image = map_renderer.generate(coordinates)
            if layout.horizontal_orientation:
                map_x = layout.width_px - map_renderer.width - layout.margin_sides_px
                map_y = layout.height_px - map_renderer.height - layout.margin_bottom_px
            else:
                map_x = layout.margin_sides_px
                map_y = calendar_y + calendar_height + layout.spacing_px
            composition.paste(map_image, (map_x, map_y))

        if config.layout.usePhotoDescription.value and not no_description_flag:
            alignment = "middle" if is_title else "left"
            description_image = description_renderer.generate(processed_description, alignment)
            _, description_height = description_image.size
            if (
                (config.calendar.useCalendar.value or bool(layout.composition_title))
                and not no_calendar_flag
                and layout.horizontal_orientation
            ):
                description_y = (
                    layout.height_px
                    - layout.calendar_primary_dim_px
                    - description_height
                    - layout.margin_bottom_px
                )
            else:
                description_y = layout.height_px - description_height - layout.margin_bottom_px
            composition.alpha_composite(description_image, (0, description_y))

        if not photos:
            context.logger.info("No pictures found.")
            return composition

        photo_images = []
        for photo in photos:
            image = photo.get_image()
            if image is None:
                raise OSError(f"Could not load photo image: {photo.file_path}")
            photo_images.append(image)
        collage = collage_renderer.generate(photo_images)
        collage_x = layout.margin_sides_px
        collage_y = layout.margin_top_px
        if not layout.horizontal_orientation and not is_title and not no_calendar_flag:
            collage_x += layout.calendar_primary_dim_px + layout.spacing_px
        composition.paste(collage, (collage_x, collage_y))

        if not is_title and not no_calendar_flag:
            date_text = get_photo_dates(photos)
            draw = ImageDraw.Draw(composition)
            font = config.style.fontAnniversaries.value.get_image_font(layout.dpi)
            draw.text(
                (
                    layout.width_px - layout.margin_sides_px,
                    layout.height_px - layout.margin_bottom_px,
                ),
                date_text,
                font=font,
                fill=text_color,
                anchor="rd",
            )

        return composition.convert("RGB")
