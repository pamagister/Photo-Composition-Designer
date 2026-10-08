"""Application-level workflows for rendering photo compositions."""

from __future__ import annotations

import copy
from logging import Logger
from pathlib import Path

from PIL import Image

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.base import CompositionDesigner


class CompositionWorkflow:
    """Coordinate composition generation without depending on the GUI."""

    def __init__(
        self,
        config: ConfigParameterManager,
        logger: Logger,
        designer: CompositionDesigner,
    ) -> None:
        """Initialize the workflow with shared configuration and renderer.

        Args:
            config: Active application configuration.
            logger: Logger used for workflow messages.
            designer: Renderer instance shared with the GUI progress callback.
        """
        self.config = config
        self.logger = logger
        self.designer = designer

    def generate(self, mode: str = "render_and_pdf") -> None:
        """Generate compositions according to the selected output mode.

        Args:
            mode: One of ``render_and_pdf``, ``render_only``, or ``pdf_only``.

        The current PDF setting is restored if rendering fails.
        """
        if mode == "render_and_pdf":
            self.designer.generate_compositions_from_folders()
        elif mode == "render_only":
            original_pdf_setting = self.config.layout.generatePdf.value
            self.config.layout.generatePdf.value = False
            try:
                self.designer.generate_compositions_from_folders()
            finally:
                self.config.layout.generatePdf.value = original_pdf_setting
        elif mode == "pdf_only":
            self.designer.generate_pdf(self.designer.outputDir)
        else:
            self.logger.warning(f"Unknown composition mode: {mode}")

    def create_preview(
        self, folder_name: str, target_width: int, target_height: int
    ) -> Image.Image | None:
        """Render a scaled preview that fits within the requested dimensions.

        Args:
            folder_name: Name of the photo folder to render.
            target_width: Maximum preview width in pixels.
            target_height: Maximum preview height in pixels.

        Returns:
            The rendered image, or ``None`` if the folder contains no photos.
        """
        size_designer = CompositionDesigner(self.config, self.logger)
        preview_scale_factor = max(
            0.1,
            min(
                target_width / size_designer.width_px,
                target_height / size_designer.height_px,
            ),
        )

        preview_config = copy.deepcopy(self.config)
        preview_config.size.dpi.value = self.config.size.dpi.value * preview_scale_factor
        preview_designer = CompositionDesigner(preview_config, self.logger)
        return preview_designer.generate_compositions_from_folder(folder_name)

    def render_and_save_preview(self, folder_name: str) -> Path | None:
        """Render a full-size composition preview and save it to the output folder.

        Args:
            folder_name: Name of the photo folder to render.

        Returns:
            The saved image path, or ``None`` if the folder contains no photos.
        """
        preview_designer = CompositionDesigner(self.config, self.logger)
        preview_image = preview_designer.generate_compositions_from_folder(folder_name)
        if preview_image is None:
            return None

        output_file = preview_designer.outputDir / f"{folder_name}.jpg"
        preview_image.save(output_file, quality=95)
        return output_file
