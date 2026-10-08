# Photo_Composition_Designer/core/base.py
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from logging import Logger
from pathlib import Path

from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image

from Photo_Composition_Designer.common.Locations import Locations
from Photo_Composition_Designer.common.Photo import Photo
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.composition_builder import (
    CompositionRenderComponents,
    CompositionRendererBuilder,
)
from Photo_Composition_Designer.core.composition_io import CompositionIO
from Photo_Composition_Designer.core.composition_layout import CompositionLayout
from Photo_Composition_Designer.image.CalendarRenderer import CalendarRenderer
from Photo_Composition_Designer.image.CollageRenderer import CollageRenderer
from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer
from Photo_Composition_Designer.image.MapRenderer import MapRenderer
from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.tools.Helpers import mm_to_px


class CompositionDesigner:
    """Coordinate composition input/output while preserving the legacy API."""

    def __init__(
        self,
        config: ConfigParameterManager | None,
        logger: Logger | None = None,
        render_components: CompositionRenderComponents | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        self.config = config or ConfigParameterManager()
        self.progress_callback = progress_callback
        if logger:
            self.logger = logger
        else:
            initialize_logging()
            self.logger = get_logger("base")

        self.photoDir: Path = Path(self.config.general.photoDirectory.value).expanduser().resolve()
        self.outputDir: Path = (self.photoDir.parent / "collages").resolve()
        self.outputDir.mkdir(parents=True, exist_ok=True)

        # Load location metadata once and share it with the composition file service.
        locations_cfg_path = Path(self.config.general.locationsConfig.value)
        self.locations = Locations(locations_cfg_path).locations_dict

        self.file_io = CompositionIO(
            self.config,
            self.photoDir,
            self.outputDir,
            self.locations,
            self.logger,
            int(self.config.size.dpi.value),
        )
        self.descriptions = self._get_description(self.photoDir)

        components = (
            render_components
            if render_components is not None
            else CompositionRendererBuilder(self.config, self.logger).build()
        )
        self.dpi = components.dpi
        self.compositionTitle = components.composition_title
        self.width_px = components.width_px
        self.height_px = components.height_px
        self.use_object_recognition = components.use_object_recognition
        self.margin_top_px = components.margin_top_px
        self.margin_bottom_px = components.margin_bottom_px
        self.margin_sides_px = components.margin_sides_px
        self.spacing_px = components.spacing_px
        self.horizontal_orientation = components.horizontal_orientation
        self.calendar_primary_dim_px = components.calendar_primary_dim_px
        self.calendar_secondary_dim_px = components.calendar_secondary_dim_px
        self.calendarObj: CalendarRenderer = components.calendar_renderer
        self.mapGenerator: MapRenderer = components.map_renderer
        self.descGenerator: DescriptionRenderer = components.description_renderer
        self.object_detector: ObjectDetector | None = components.object_detector
        self.layout: CompositionLayout = components.layout
        self.layoutManager: CollageRenderer = components.collage_renderer
        self.page_renderer = components.page_renderer
        self._mm_to_px = lambda mm: mm_to_px(mm, self.dpi)

        start_date_cfg = self.config.calendar.startDate.value
        if self.compositionTitle:
            self.startDate = start_date_cfg - timedelta(days=7)
        else:
            self.startDate = start_date_cfg

    # ---------------------------------------------------------------------
    # Helpers: unit conversions & derived sizes
    # ---------------------------------------------------------------------
    def get_available_collage_width_px(self) -> int:
        return self.layout.get_available_collage_width_px()

    def get_available_collage_height_px(
        self, no_calendar_flag: bool, no_description_flag: bool
    ) -> int:
        return self.layout.get_available_collage_height_px(no_calendar_flag, no_description_flag)

    def _process_photo_description(self, photo_description: str) -> tuple[str, bool, bool]:
        return CompositionLayout.process_photo_description(photo_description)

    # ---------------------------------------------------------------------
    # Composition rendering
    # ---------------------------------------------------------------------
    def _generate_composition(
        self,
        photos: list[Photo],
        date: datetime,
        photo_description: str = "",
        is_title: bool = False,
    ) -> Image.Image:
        """Render a page using the dedicated page renderer."""
        return self.page_renderer.render(
            photos,
            date,
            photo_description,
            is_title=is_title,
        )

    @staticmethod
    def _get_description(folder_path: Path) -> list[str]:
        """Read the optional global or folder-level text description."""
        return CompositionIO.get_description(folder_path)

    def generate_compositions_from_folder(
        self,
        folder_name: str,
    ) -> Image.Image | None:
        """
        Generates a single collage for the given folder name.
        Returns True if a composition was generated, False if skipped.
        """
        folder_path = self.photoDir / folder_name
        if not folder_path.is_dir():
            self.logger.info(f"{folder_path} is not a valid directory. Skipping...")
            return None

        folder_names = self.file_io.get_photo_folders()
        try:
            week_index = folder_names.index(folder_name)
        except ValueError:
            self.logger.info(f"Folder '{folder_name}' not found in photoDirectory (unexpected).")
            return None
        return self._generate_composition_from_folder(folder_name, week_index)

    def _generate_composition_from_folder(
        self, folder_name: str, week_index: int
    ) -> Image.Image | None:
        """Load one photo folder and render it using its chronological position."""
        folder_path = self.photoDir / folder_name
        if not folder_path.is_dir():
            self.logger.info(f"{folder_path} is not a valid directory. Skipping...")
            return None

        photos = self.file_io.load_photos(folder_path)
        if not photos:
            self.logger.info(f"No images found in {folder_path}, skipping...")
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

    def generate_compositions_from_folders(self) -> None:
        """Render and save every photo folder, reporting progress when configured."""
        folder_names = self.file_io.get_photo_folders()
        total = len(folder_names)

        if self.progress_callback is not None:
            self.progress_callback(0, total)

        for idx, folder_name in enumerate(folder_names, start=1):
            self.logger.info(f"Processing folder: {folder_name}")

            composition = self._generate_composition_from_folder(folder_name, idx - 1)
            if composition:
                self.save(composition, folder_name)

            if self.progress_callback is not None:
                self.progress_callback(idx, total)

        if self.config.layout.generatePdf.value:
            self.generate_pdf(self.outputDir)

    def save(self, composition: Image.Image, element: str) -> None:
        """Persist one composition in the configured output directory."""
        self.file_io.save(composition, element)

    def generate_pdf(self, collages_dir: Path | str, output_pdf: str = "output.pdf") -> Path | None:
        """Create a PDF from rendered images, if any are present."""
        return self.file_io.generate_pdf(collages_dir, output_pdf)


if __name__ == "__main__":
    # Example usage: read default config (or pass path to config file)
    cfg_file = None
    # If you want to use a specific config file, you can set cfg_file = "config/config.yaml"
    cfg = ConfigParameterManager(cfg_file)
    cd = CompositionDesigner(cfg)
    cd.generate_compositions_from_folders()
