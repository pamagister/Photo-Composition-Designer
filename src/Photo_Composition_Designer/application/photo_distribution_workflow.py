"""Application-level workflow for distributing photos into dated folders."""

from __future__ import annotations

import os
import shutil
from datetime import timedelta
from logging import Logger
from pathlib import Path

from Photo_Composition_Designer.common.Photo import Photo, get_photos_from_dir
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.tools.ImageDistributor import ImageDistributor


class PhotoDistributionWorkflow:
    """Distribute source photos into the configured composition folders."""

    def __init__(self, config: ConfigParameterManager, logger: Logger) -> None:
        """Initialize the workflow.

        Args:
            config: Active application configuration.
            logger: Logger used for workflow messages.
        """
        self.config = config
        self.logger = logger

    def distribute(self, photo_directory: Path, mode: str) -> bool:
        """Distribute photos into dated folders.

        Args:
            photo_directory: Directory containing the source photos.
            mode: Distribution strategy selected by the user.

        Returns:
            ``True`` if photos were available for processing, otherwise ``False``.
        """
        photos: list[Photo] = get_photos_from_dir(photo_directory)
        if not photos:
            self.logger.warning(f"No photos found in directory {photo_directory}")
            return False

        collages_to_generate = self.config.calendar.collagesToGenerate.value
        image_distributor = ImageDistributor(photos, collages_to_generate)
        if mode == "distribute_equally":
            grouped_images = image_distributor.distribute_equally()
        elif mode == "distribute_randomly":
            grouped_images = image_distributor.distribute_randomly()
        elif mode == "distribute_group_matching_dates":
            grouped_images = image_distributor.distribute_group_matching_dates()
        else:
            self.logger.warning(f"Unknown mode: {mode}")
            grouped_images = []

        start_date = self.config.calendar.startDate.value
        for week in range(collages_to_generate):
            week_start = start_date + timedelta(weeks=week)
            folder_name = f"{week:02d}_{week_start.strftime('%b-%d')}"
            folder_path = photo_directory / folder_name
            os.makedirs(folder_path, exist_ok=True)
            self.logger.info(f"Folder created: {folder_path}")

            if not grouped_images:
                continue
            images_in_group = grouped_images.pop(0)
            for photo in images_in_group:
                destination_path = folder_path / photo.file_path.name
                shutil.copy2(photo.file_path, destination_path)
                self.logger.info(f"  --> Image {photo.file_path.name} sorted into {folder_name}")

        self.logger.info(f"Completed: {len(grouped_images)} files processed")
        self.logger.info("=== All files processed successfully! ===")
        return True
