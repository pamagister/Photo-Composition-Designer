# Photo_Composition_Designer/core/CompositionDesigner.py
from __future__ import annotations

import os
import re
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from Photo_Composition_Designer.common.Locations import Locations
from Photo_Composition_Designer.common.Photo import Photo, get_photos_from_dir
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.image.CalendarRenderer import (
    CalendarRenderer,
    from_config,
)
from Photo_Composition_Designer.image.CollageRenderer import CollageRenderer
from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer
from Photo_Composition_Designer.image.MapRenderer import MapRenderer
from Photo_Composition_Designer.tools.Helpers import load_font


class CompositionDesigner:
    """
    CompositionDesigner adapted to the new ConfigParameterManager.

    - Converts mm-based sizes in the config to pixels using config.size.dpi.value
    - Uses create_calendar_generator_from_config to create a CalendarGenerator
    - Accesses parameters through config.<category>.<param>.value
    """

    def __init__(self, config: ConfigParameterManager | None = None):
        self.config = config or ConfigParameterManager()
        self.dpi: int = int(self.config.size.dpi.value)

        # mm-based -> pixel helper bound to this instance
        self._mm_to_px = lambda mm: int(round(float(mm) * self.dpi / 25.4))
        self.fontSizeSmall = int(
            config.layout.fontSizeSmall.value
            * config.size.calendarHeight.value
            * config.size.dpi.value
            / 25.4
        )

        # basic properties
        self.compositionTitle: str | None = self.config.general.compositionTitle.value or ""
        self.photoDirectory: Path = (
            Path(self.config.general.photoDirectory.value).expanduser().resolve()
        )
        self.outputDir: Path = (self.photoDirectory.parent / "collages").resolve()
        os.makedirs(self.outputDir, exist_ok=True)

        # size in pixels
        self.width_px = self._mm_to_px(self.config.size.width.value)
        self.height_px = self._mm_to_px(self.config.size.height.value)

        # margins / spacing in pixels
        self.margin_top_px = self._mm_to_px(self.config.layout.marginTop.value)
        self.margin_bottom_px = self._mm_to_px(self.config.layout.marginBottom.value)
        self.margin_sides_px = self._mm_to_px(self.config.layout.marginSides.value)
        self.spacing_px = self._mm_to_px(self.config.layout.spacing.value)

        # calendar sizes
        self.calendar_height_px = self._mm_to_px(self.config.size.calendarHeight.value)
        self.map_width_px = self._mm_to_px(self.config.size.mapWidth.value)
        self.map_height_px = self._mm_to_px(self.config.size.mapHeight.value)

        # colors (Color objects have .to_pil() in your calendar factory)
        # Use the calendar factory which expects the full config object
        self.calendarObj: CalendarRenderer = from_config(self.config)

        # colors
        background_color = self.config.colors.backgroundColor.value.to_pil()
        text_color1 = self.config.colors.textColor1.value.to_pil()
        text_color2 = self.config.colors.textColor2.value.to_pil()

        # Create other helpers/generators — pass config object for them to pull values from.
        # If their constructors changed, update these lines accordingly.
        self.mapGenerator: MapRenderer = MapRenderer(
            self.map_height_px,
            self.map_width_px,
            self.config.geo.minimalExtension.value,
            background_color,
            text_color1,
        )
        self.descGenerator: DescriptionRenderer = DescriptionRenderer(
            self.width_px,
            self.fontSizeSmall,
            self.spacing_px,
            self.margin_sides_px,
            background_color,
            text_color2,
        )

        # startDate: if title present we keep the previous behavior (shift -7 days)

        # Photo layout manager expects pixel dims: width, collage_height, spacing, backgroundColor
        collage_height_px = self.get_available_collage_height_px()
        self.layoutManager: CollageRenderer = CollageRenderer(
            self.width_px, collage_height_px, self.spacing_px, background_color
        )
        start_date_cfg = self.config.calendar.startDate.value
        if self.compositionTitle:
            self.startDate = start_date_cfg - timedelta(days=7)
        else:
            self.startDate = start_date_cfg

    # ---------------------------------------------------------------------
    # Helpers: unit conversions & derived sizes
    # ---------------------------------------------------------------------
    def get_available_collage_height_px(self) -> int:
        """
        Compute available vertical space for the collage area in pixels.
        This subtracts calendar and description heights when configured.
        """
        available_height = self.height_px

        # calendar or title reduces space
        if self.config.calendar.useCalendar.value or bool(self.compositionTitle):
            available_height -= self.calendar_height_px + self.margin_bottom_px + self.margin_top_px

        # description area
        if self.config.layout.usePhotoDescription.value:
            # descGenerator should expose .height in pixels like before; if not, compute it
            desc_height = getattr(self.descGenerator, "height", None)
            if desc_height is None:
                # fallback: estimate description height using layout font sizes & calendarHeight
                desc_height = self._mm_to_px(self.config.size.calendarHeight.value // 4)
            available_height -= desc_height

        # ensure positive height
        return max(0, int(available_height))

    # ---------------------------------------------------------------------
    # Composition rendering
    # ---------------------------------------------------------------------
    def generate_composition(
        self,
        photos: list[Photo],
        date,
        photo_description: str = "",
    ) -> Image.Image:
        """
        Creates a composition with pictures, a calendar and a map of Europe with photo locations.
        """
        background_color = self.config.colors.backgroundColor.value.to_pil()
        text_color2 = self.config.colors.textColor2.value.to_pil()

        composition = Image.new("RGB", (self.width_px, self.height_px), background_color)
        available_cal_width = self.width_px

        # add title or calendar
        if self.compositionTitle:
            title_img = self.calendarObj.generateTitle(
                self.compositionTitle, available_cal_width, self.calendar_height_px
            )
            composition.paste(
                title_img, (self.margin_sides_px, self.height_px - self.calendar_height_px)
            )
        elif self.config.calendar.useCalendar.value and not self.compositionTitle:
            if self.config.geo.usePhotoLocationMaps.value:
                available_cal_width -= self.map_width_px + self.margin_sides_px
            calendar_img = self.calendarObj.generate(
                date, available_cal_width, self.calendar_height_px
            )
            composition.paste(
                calendar_img,
                (
                    self.margin_sides_px,
                    self.height_px - self.calendar_height_px - self.margin_bottom_px,
                ),
            )

        # description area
        if self.config.layout.usePhotoDescription.value:
            description_img = self.descGenerator.generate(photo_description)
            desc_h = getattr(self.descGenerator, "height", description_img.size[1])
            composition.paste(
                description_img,
                (
                    0,
                    self.height_px - self.calendar_height_px - desc_h - self.margin_bottom_px,
                ),
            )

        if len(photos) == 0:
            print("No pictures found.")
            return composition

        # Arrange image composition
        collage = self.layoutManager.generate([photo.get_image() for photo in photos])
        composition.paste(collage, (0, self.margin_top_px))

        # add location map (if configured and not the title page)
        if self.config.geo.usePhotoLocationMaps.value and not self.compositionTitle:
            coordinates = [loc for photo in photos if (loc := photo.get_location()) is not None]
            imgMap = self.mapGenerator.generate(coordinates)
            composition.paste(
                imgMap,
                (
                    self.width_px - self.map_width_px - self.margin_sides_px,
                    self.height_px - self.map_height_px - self.margin_bottom_px,
                ),
            )

        # draw dates of images into lower-right corner (max 3 unique dates)
        image_dates = [d for photo in photos if (d := photo.get_date()) is not None]
        unique_dates = set()
        date_str = ""
        for d in image_dates:
            formatted = d.strftime("%d. %b ")
            if formatted not in unique_dates:
                unique_dates.add(formatted)
                date_str += formatted
            if len(unique_dates) >= 3:
                break

        draw = ImageDraw.Draw(composition)

        # Build small font size in px:
        # In CalendarGenerator factory you used:
        # font_px = layout.fontSizeSmall.value * size.calendarHeight.value * dpi / 25.4
        font_small_px = int(
            float(self.config.layout.fontSizeSmall.value)
            * float(self.config.size.calendarHeight.value)
            * self.dpi
            / 25.4
            * 0.8
        )
        # fallback
        if font_small_px <= 0:
            font_small_px = max(10, int(self.dpi * 0.04))

        font = load_font("DejaVuSans.ttf", font_small_px)

        # Anchor rd expects coordinates relative to lower-right;
        # to put text inside margins we shift left/up
        x = self.width_px - self.margin_sides_px
        y = self.height_px - self.margin_bottom_px
        draw.text((x, y), date_str, font=font, fill=text_color2, anchor="rd")

        # create title only once
        self.compositionTitle = None

        return composition

    @staticmethod
    def _get_description(folder_path: Path, fallback_to_foldername: bool = False):
        """
        Search for a .txt file in the folder and return list(lines) without leading 'Label: ' parts.
        Returns empty string or list when none found.
        """
        photo_description = ""
        text_files = [
            folder_path / file
            for file in sorted(os.listdir(folder_path))
            if file.lower().endswith(".txt")
        ]
        if text_files:
            text_file = text_files[0]
            with open(text_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                photo_description = [re.sub(r"^[^:]*:\s*", "", line) for line in lines]
            if not photo_description and fallback_to_foldername:
                photo_description = [text_file.stem]
        return photo_description

    def generate_compositions_from_folders(self):
        """
        Generates collages for all weeks from the specified folder.
        """
        descriptions = self._get_description(self.photoDirectory) or []
        weekIndex = 0

        # load locations config path and create Locations instance
        locations_cfg_path = Path(self.config.general.locationsConfig.value)
        locations = Locations(locations_cfg_path).locations_dict

        for element in sorted(os.listdir(self.photoDirectory)):
            folder_path = self.photoDirectory / element
            if not folder_path.is_dir():
                continue

            photos = get_photos_from_dir(folder_path, locations)
            if not photos:
                print(f"No images found in {folder_path}, skip...")
                continue

            # description precedence: per-folder text overrides global descriptions list
            description = descriptions[weekIndex] if weekIndex < len(descriptions) else ""
            folder_desc = self._get_description(folder_path, fallback_to_foldername=True)
            if folder_desc:
                description = folder_desc

            start_date = self.startDate + timedelta(weeks=weekIndex)

            # choose description (list support)
            if isinstance(description, (list, tuple)):
                collage_description = description[0] if 0 < len(description) else ""
            else:
                collage_description = description if isinstance(description, str) else ""

            composition = self.generate_composition(photos, start_date, collage_description)

            # save with configured quality/dpi
            output_prefix = f"collage_{element}"
            output_file_name = f"{output_prefix}.jpg"
            output_path = self.outputDir / output_file_name
            jpg_quality = int(self.config.size.jpgQuality.value)
            dpi_tuple = (self.dpi, self.dpi)
            composition.save(output_path, quality=jpg_quality, dpi=dpi_tuple)
            print(f"Composition saved: {output_path}")

            weekIndex += 1

        if self.config.layout.generatePdf.value:
            self.generate_pdf(self.outputDir)

    def generate_pdf(self, collages_dir: Path | str, output_pdf: str = "output.pdf"):
        """
        Creates a PDF file from all images in a directory.
        """
        collages_dir = Path(collages_dir)
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}

        image_files = sorted(
            [
                f
                for f in os.listdir(collages_dir)
                if os.path.splitext(f)[1].lower() in image_extensions
            ]
        )

        if not image_files:
            print("No images found in the directory.")
            return

        image_list: list[Image.Image] = []
        for image_file in image_files:
            img_path = collages_dir / image_file
            img = Image.open(img_path).convert("RGB")
            image_list.append(img)

        first_image, *remaining_images = image_list
        output_path = collages_dir / output_pdf
        first_image.save(
            str(output_path),
            save_all=True,
            append_images=remaining_images,
            quality=int(self.config.size.jpgQuality.value),
            dpi=(self.dpi, self.dpi),
        )
        print(f"PDF successfully created: {output_path}")


if __name__ == "__main__":
    # Example usage: read default config (or pass path to config file)
    cfg_file = None
    # If you want to use a specific config file, you can set cfg_file = "config/config.yaml"
    cfg = ConfigParameterManager(cfg_file)
    # cfg.general.photoDirectory =
    cd = CompositionDesigner(cfg)
    cd.generate_compositions_from_folders()
