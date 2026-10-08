"""File-system operations used by composition generation."""

from __future__ import annotations

import os
import re
from logging import Logger
from pathlib import Path
from typing import Protocol

from PIL import Image

from Photo_Composition_Designer.common.Photo import Photo, get_photos_from_dir
from Photo_Composition_Designer.config.config import ConfigParameterManager


class CompositionFileOperations(Protocol):
    """File-system boundary required by the composition coordinator."""

    photo_dir: Path
    output_dir: Path
    locations: dict[str, tuple[float, float]]

    def get_description(self, folder_path: Path) -> list[str]: ...

    def get_photo_folders(self) -> list[str]: ...

    def load_photos(self, folder_path: Path) -> list[Photo]: ...

    def save(self, composition: Image.Image, element: str) -> Path: ...

    def generate_pdf(
        self, collages_dir: Path | str, output_pdf: str = "output.pdf"
    ) -> Path | None: ...


class CompositionIO:
    """Load composition inputs and persist rendered image outputs."""

    def __init__(
        self,
        config: ConfigParameterManager,
        photo_dir: Path,
        output_dir: Path,
        locations: dict[str, tuple[float, float]],
        logger: Logger,
        dpi: int,
    ) -> None:
        """Initialize file operations with application configuration and paths."""
        self.config = config
        self.photo_dir = photo_dir
        self.output_dir = output_dir
        self.locations = locations
        self.logger = logger
        self.dpi = dpi

    @staticmethod
    def get_description(folder_path: Path) -> list[str]:
        """Read the first sorted text file and strip optional label prefixes."""
        photo_description = [""]
        if not folder_path.exists():
            return photo_description

        text_files = sorted(
            folder_path / filename
            for filename in os.listdir(folder_path)
            if filename.lower().endswith(".txt")
        )
        if text_files:
            text_file = text_files[0]
            with text_file.open("r", encoding="utf-8") as description_file:
                lines = [line.strip() for line in description_file.readlines() if line.strip()]
            photo_description = [re.sub(r"^[^:]*:\s*", "", line) for line in lines]
            if not photo_description:
                photo_description = [text_file.stem]

        return photo_description

    def get_photo_folders(self) -> list[str]:
        """Return sorted names of subdirectories in the configured photo folder."""
        return sorted(entry.name for entry in self.photo_dir.iterdir() if entry.is_dir())

    def load_photos(self, folder_path: Path) -> list[Photo]:
        """Load photos from one folder using the configured location metadata."""
        return get_photos_from_dir(folder_path, self.locations)

    def save(self, composition: Image.Image, element: str) -> Path:
        """Save a composition as a JPEG and return its path."""
        output_path = self.output_dir / f"{element}.jpg"
        composition.save(
            output_path,
            quality=int(self.config.size.jpgQuality.value),
            dpi=(self.dpi, self.dpi),
        )
        self.logger.info(f"Composition saved: {output_path}")
        return output_path

    def generate_pdf(self, collages_dir: Path | str, output_pdf: str = "output.pdf") -> Path | None:
        """Combine sorted image files into a PDF, returning ``None`` when empty."""
        directory = Path(collages_dir)
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}
        image_files = sorted(
            filename
            for filename in os.listdir(directory)
            if Path(filename).suffix.lower() in image_extensions
        )

        if not image_files:
            self.logger.info("No images found in the directory.")
            return None

        image_list: list[Image.Image] = []
        for image_file in image_files:
            with Image.open(directory / image_file) as image:
                image_list.append(image.convert("RGB"))

        first_image, *remaining_images = image_list
        output_path = directory / output_pdf
        first_image.save(
            str(output_path),
            save_all=True,
            append_images=remaining_images,
            quality=int(self.config.size.jpgQuality.value),
            dpi=(self.dpi, self.dpi),
        )
        self.logger.info(f"PDF successfully created: {output_path}")
        return output_path
