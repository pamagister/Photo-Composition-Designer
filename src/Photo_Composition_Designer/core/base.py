# Photo_Composition_Designer/core/base.py
from __future__ import annotations

import os
import re
from datetime import timedelta
from logging import Logger
from pathlib import Path

from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image, ImageDraw

from Photo_Composition_Designer.common.Locations import Locations
from Photo_Composition_Designer.common.Photo import Photo, get_photo_dates, get_photos_from_dir
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.image.CalendarRenderer import CalendarRenderer
from Photo_Composition_Designer.image.CollageRenderer import CollageRenderer
from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer
from Photo_Composition_Designer.image.MapRenderer import MapRenderer
from Photo_Composition_Designer.tools.Helpers import mm_to_px


class CompositionDesigner:
    """
    CompositionDesigner adapted to the new ConfigParameterManager.

    - Converts mm-based sizes in the config to pixels using config.size.dpi.value
    - Uses create_calendar_generator_from_config to create a CalendarGenerator
    - Accesses parameters through config.<category>.<param>.value
    """

    def __init__(self, config: ConfigParameterManager | None, logger: Logger = None):
        self.config = config or ConfigParameterManager()
        if logger:
            self.logger: Logger = logger
        else:
            initialize_logging()
            self.logger: Logger = get_logger("base")

        self.dpi: int = int(self.config.size.dpi.value)
        # load locations config path and create Locations instance
        locations_cfg_path = Path(self.config.general.locationsConfig.value)
        self.locations = Locations(locations_cfg_path).locations_dict

        # mm-based -> pixel helper bound to this instance
        self._mm_to_px = lambda mm: mm_to_px(mm, self.dpi)

        # basic properties
        self.compositionTitle: str | None = self.config.general.compositionTitle.value or ""
        self.photoDir: Path = Path(self.config.general.photoDirectory.value).expanduser().resolve()
        self.outputDir: Path = (self.photoDir.parent / "collages").resolve()
        os.makedirs(self.outputDir, exist_ok=True)
        self.descriptions = self._get_description(self.photoDir)

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

        # colors (Color objects have .to_pil() in your calendar factory)
        # Use the calendar factory which expects the full config object
        self.calendarObj: CalendarRenderer = CalendarRenderer.from_config(self.config)

        # colors
        background_color = self.config.style.backgroundColor.value.to_pil()

        # Create other helpers/generators — pass config object for them to pull values from.
        self.mapGenerator: MapRenderer = MapRenderer.from_config(self.config)
        self.descGenerator: DescriptionRenderer = DescriptionRenderer.from_config(self.config)

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
    def _generate_composition(
        self,
        photos: list[Photo],
        date,
        photo_description: str = "",
        is_title=False,
    ) -> Image.Image:
        """
        Creates a composition with pictures, a calendar and a map of Europe with photo locations.
        """
        background_color = self.config.style.backgroundColor.value.to_pil()
        text_color2 = self.config.style.fontSmall.value.color.to_pil()

        composition = Image.new("RGB", (self.width_px, self.height_px), background_color)
        available_cal_width = self.width_px

        # add title or calendar
        if is_title and self.compositionTitle:
            title_img = self.calendarObj.generateTitle(
                self.compositionTitle, available_cal_width, self.calendar_height_px
            )
            composition.paste(
                title_img, (self.margin_sides_px, self.height_px - self.calendar_height_px)
            )
        elif self.config.calendar.useCalendar.value:
            if self.config.geo.usePhotoLocationMaps.value:
                available_cal_width -= self.mapGenerator.width + self.margin_sides_px
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
            self.logger.info("No pictures found.")
            return composition

        # Arrange image composition
        collage = self.layoutManager.generate([photo.get_image() for photo in photos])
        composition.paste(collage, (0, self.margin_top_px))

        # add location map (if configured and not the title page)
        if self.config.geo.usePhotoLocationMaps.value and not is_title:
            coordinates = [loc for photo in photos if (loc := photo.get_location()) is not None]
            imgMap = self.mapGenerator.generate(coordinates)
            composition.paste(
                imgMap,
                (
                    self.width_px - self.mapGenerator.width - self.margin_sides_px,
                    self.height_px - self.mapGenerator.height - self.margin_bottom_px,
                ),
            )

        # draw the image dates in
        date_str = get_photo_dates(photos)
        draw = ImageDraw.Draw(composition)
        font = self.config.style.fontAnniversaries.value.get_image_font(self.dpi)

        # Anchor rd expects coordinates relative to lower-right;
        # to put text inside margins we shift left/up
        x = self.width_px - self.margin_sides_px
        y = self.height_px - self.margin_bottom_px
        draw.text((x, y), date_str, font=font, fill=text_color2, anchor="rd")

        return composition

    @staticmethod
    def _get_description(folder_path: Path) -> list[str]:
        """
        Search for a .txt file in the folder and return list(lines) without leading 'Label: ' parts.
        Returns empty string or list when none found.
        """
        photo_description: list[str] = [""]
        if not folder_path.exists():
            return photo_description
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
            if not photo_description:
                photo_description = [text_file.stem]
        return photo_description

    def generate_compositions_from_folder(self, folder_name: str) -> Image.Image | None:
        """
        Generates a single collage for the given folder name.
        Returns True if a composition was generated, False if skipped.
        """
        folder_path = self.photoDir / folder_name

        if not folder_path.is_dir():
            self.logger.info(f"{folder_path} is not a valid directory. Skipping...")
            return None

        # Extract photos
        photos = get_photos_from_dir(folder_path, self.locations)
        if not photos:
            self.logger.info(f"No images found in {folder_path}, skipping...")
            return None

        # Determine description (folder-level overrides global)
        # Week index must be inferred from folder ordering
        sorted_folders = sorted(
            [f for f in os.listdir(self.photoDir) if (self.photoDir / f).is_dir()]
        )
        try:
            week_index = sorted_folders.index(folder_name)
        except ValueError:
            self.logger.info(f"Folder '{folder_name}' not found in photoDirectory (unexpected).")
            return None

        global_description = (
            self.descriptions[week_index] if week_index < len(self.descriptions) else ""
        )
        collage_description: str = self._get_description(folder_path)[0] or global_description

        start_date = self.startDate + timedelta(weeks=week_index)

        composition = self._generate_composition(
            photos, start_date, collage_description, is_title=week_index == 0
        )

        return composition

    def generate_compositions_from_folders(self):
        sorted_folders = sorted(
            [f for f in os.listdir(self.photoDir) if (self.photoDir / f).is_dir()]
        )

        total = len(sorted_folders)

        # Initialer Fortschritt
        if hasattr(self, "progress_callback"):
            self.progress_callback(0, total)

        for idx, folder_name in enumerate(sorted_folders, start=1):
            self.logger.info(f"Processing folder: {folder_name}")

            composition = self.generate_compositions_from_folder(folder_name)
            if composition:
                self.save(composition, folder_name)

            # Fortschritt melden
            if hasattr(self, "progress_callback"):
                self.progress_callback(idx, total)

        if self.config.layout.generatePdf.value:
            self.generate_pdf(self.outputDir)

    def save(self, composition: Image.Image, element: str):
        # save with configured quality/dpi
        output_prefix = f"collage_{element}"
        output_file_name = f"{output_prefix}.jpg"
        output_path = self.outputDir / output_file_name
        jpg_quality = int(self.config.size.jpgQuality.value)
        dpi_tuple = (self.dpi, self.dpi)
        composition.save(output_path, quality=jpg_quality, dpi=dpi_tuple)
        self.logger.info(f"Composition saved: {output_path}")

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
            self.logger.info("No images found in the directory.")
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
        self.logger.info(f"PDF successfully created: {output_path}")


if __name__ == "__main__":
    # Example usage: read default config (or pass path to config file)
    cfg_file = None
    # If you want to use a specific config file, you can set cfg_file = "config/config.yaml"
    cfg = ConfigParameterManager(cfg_file)
    cd = CompositionDesigner(cfg)
    cd.generate_compositions_from_folders()
