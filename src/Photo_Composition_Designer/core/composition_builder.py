"""Construction of the rendering dependency graph for a composition."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.composition_layout import CompositionLayout
from Photo_Composition_Designer.core.composition_renderer import (
    CompositionPageRenderer,
    CompositionRenderContext,
)
from Photo_Composition_Designer.image.CalendarRenderer import CalendarRenderer
from Photo_Composition_Designer.image.CollageRenderer import CollageRenderer
from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer
from Photo_Composition_Designer.image.MapRenderer import MapRenderer
from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.tools.Helpers import mm_to_px


@dataclass(frozen=True)
class CompositionRenderComponents:
    """Rendering collaborators and derived page geometry for a composition."""

    dpi: int
    composition_title: str
    width_px: int
    height_px: int
    use_object_recognition: bool
    margin_top_px: int
    margin_bottom_px: int
    margin_sides_px: int
    spacing_px: int
    horizontal_orientation: bool
    calendar_primary_dim_px: int
    calendar_secondary_dim_px: int
    calendar_renderer: CalendarRenderer
    map_renderer: MapRenderer
    description_renderer: DescriptionRenderer
    object_detector: ObjectDetector | None
    layout: CompositionLayout
    collage_renderer: CollageRenderer
    page_renderer: CompositionPageRenderer


class CompositionRendererBuilder:
    """Build and wire the collaborators required for rendering composition pages."""

    def __init__(self, config: ConfigParameterManager, logger: Logger) -> None:
        """Initialize the builder with the application configuration and logger."""
        self.config = config
        self.logger = logger

    def build(self) -> CompositionRenderComponents:
        """Create renderer collaborators and derive their shared page geometry."""
        config = self.config
        dpi = int(config.size.dpi.value)

        def mm_to_pixels(value: float) -> int:
            return mm_to_px(value, dpi)

        composition_title = config.general.compositionTitle.value or ""
        width_px = mm_to_pixels(config.size.width.value)
        height_px = mm_to_pixels(config.size.height.value)
        margin_top_px = mm_to_pixels(config.layout.marginTop.value)
        margin_bottom_px = mm_to_pixels(config.layout.marginBottom.value)
        margin_sides_px = mm_to_pixels(config.layout.marginSides.value)
        spacing_px = mm_to_pixels(config.layout.spacing.value)
        horizontal_orientation = config.calendar.horizontalOrientation.value
        calendar_primary_dim_px = mm_to_pixels(config.size.calendarHeight.value)
        if horizontal_orientation:
            calendar_secondary_dim_px = width_px - (2 * margin_sides_px)
        else:
            calendar_secondary_dim_px = height_px - margin_top_px - margin_bottom_px

        calendar_renderer = CalendarRenderer.from_config(config)
        map_renderer = MapRenderer.from_config(config)
        description_renderer = DescriptionRenderer.from_config(config)
        use_object_recognition = config.layout.objectRecognition
        object_detector = ObjectDetector() if use_object_recognition else None
        layout = CompositionLayout(
            config=config,
            width_px=width_px,
            height_px=height_px,
            dpi=dpi,
            margin_top_px=margin_top_px,
            margin_bottom_px=margin_bottom_px,
            margin_sides_px=margin_sides_px,
            spacing_px=spacing_px,
            calendar_primary_dim_px=calendar_primary_dim_px,
            calendar_secondary_dim_px=calendar_secondary_dim_px,
            horizontal_orientation=horizontal_orientation,
            composition_title=composition_title,
            description_renderer=description_renderer,
        )
        collage_renderer = CollageRenderer(
            layout.get_available_collage_width_px(),
            layout.get_available_collage_height_px(False, False),
            spacing_px,
            config.style.backgroundColor.value.to_pil(),
            use_object_recognition,
            config.layout.useRoundedCorners.value,
            config.layout.imageScoreFactor.value,
            object_detector,
        )
        page_renderer = CompositionPageRenderer(
            CompositionRenderContext(
                config=config,
                logger=self.logger,
                layout=layout,
                calendar_renderer=calendar_renderer,
                collage_renderer=collage_renderer,
                description_renderer=description_renderer,
                map_renderer=map_renderer,
            )
        )

        return CompositionRenderComponents(
            dpi=dpi,
            composition_title=composition_title,
            width_px=width_px,
            height_px=height_px,
            use_object_recognition=use_object_recognition,
            margin_top_px=margin_top_px,
            margin_bottom_px=margin_bottom_px,
            margin_sides_px=margin_sides_px,
            spacing_px=spacing_px,
            horizontal_orientation=horizontal_orientation,
            calendar_primary_dim_px=calendar_primary_dim_px,
            calendar_secondary_dim_px=calendar_secondary_dim_px,
            calendar_renderer=calendar_renderer,
            map_renderer=map_renderer,
            description_renderer=description_renderer,
            object_detector=object_detector,
            layout=layout,
            collage_renderer=collage_renderer,
            page_renderer=page_renderer,
        )
