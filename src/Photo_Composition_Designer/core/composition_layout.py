"""Page geometry and description options for photo compositions."""

from __future__ import annotations

from dataclasses import dataclass

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer
from Photo_Composition_Designer.tools.Helpers import mm_to_px


@dataclass(frozen=True)
class CompositionLayout:
    """Provide pixel dimensions and available collage space for a page."""

    config: ConfigParameterManager
    width_px: int
    height_px: int
    dpi: int
    margin_top_px: int
    margin_bottom_px: int
    margin_sides_px: int
    spacing_px: int
    calendar_primary_dim_px: int
    calendar_secondary_dim_px: int
    horizontal_orientation: bool
    composition_title: str
    description_renderer: DescriptionRenderer

    def get_available_collage_width_px(self) -> int:
        """Return the page width remaining for the photo collage."""
        available_width = self.width_px - 2 * self.margin_sides_px

        if not self.horizontal_orientation and (
            self.config.calendar.useCalendar.value or bool(self.composition_title)
        ):
            available_width -= self.calendar_primary_dim_px + self.spacing_px

        return int(available_width)

    def get_available_collage_height_px(
        self, no_calendar_flag: bool, no_description_flag: bool
    ) -> int:
        """Return the page height remaining for the photo collage."""
        available_height = self.height_px - self.margin_bottom_px - self.margin_top_px

        if (
            self.config.calendar.useCalendar.value or bool(self.composition_title)
        ) and not no_calendar_flag:
            if self.horizontal_orientation:
                available_height -= self.calendar_primary_dim_px

        if self.config.layout.usePhotoDescription.value and not no_description_flag:
            description_height = getattr(self.description_renderer, "height", None)
            if description_height is None:
                description_height = mm_to_px(self.config.size.calendarHeight.value // 4, self.dpi)
            available_height -= description_height

        return max(0, int(available_height))

    @staticmethod
    def process_photo_description(photo_description: str) -> tuple[str, bool, bool]:
        """Remove composition tags and return their corresponding flags."""
        no_calendar = "[no-calendar]" in photo_description
        no_description = "[no-description]" in photo_description
        cleaned_description = (
            photo_description.replace("[no-calendar]", "").replace("[no-description]", "").strip()
        )

        if not cleaned_description:
            no_description = True

        return cleaned_description, no_calendar, no_description
