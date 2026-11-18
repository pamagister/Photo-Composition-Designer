"""Factory for creating composition designers at application boundaries."""

from __future__ import annotations

from collections.abc import Callable
from logging import Logger
from pathlib import Path

from photo_composition_designer.core.composition_builder import (
    CompositionRenderComponents,
    CompositionRendererBuilder,
)
from photo_composition_designer.core.composition_designer import CompositionDesigner
from photo_composition_designer.core.composition_io import (
    CompositionFileOperations,
    CompositionIO,
)
from photo_composition_designer.core.locations import Locations
from photo_composition_designer.core.settings import Settings as ConfigParameterManager

ProgressCallback = Callable[[int, int], None]


class CompositionDesignerFactory:
    """Create composition designers with consistent application dependencies."""

    def create(
        self,
        config: ConfigParameterManager,
        logger: Logger,
        progress_callback: ProgressCallback | None = None,
        file_io: CompositionFileOperations | None = None,
        render_components: CompositionRenderComponents | None = None,
    ) -> CompositionDesigner:
        """Create a designer with its infrastructure dependencies assembled."""
        if file_io is None:
            photo_dir = Path(config.general.photoDirectory.value).expanduser().resolve()
            output_dir = (photo_dir.parent / "collages").resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            locations_path = Path(config.general.locationsConfig.value)
            locations = Locations(locations_path).locations_dict
            file_io = CompositionIO(
                config,
                photo_dir,
                output_dir,
                locations,
                logger,
                int(config.size.dpi.value),
            )

        if render_components is None:
            render_components = CompositionRendererBuilder(config, logger).build()

        return CompositionDesigner(
            config,
            logger,
            render_components=render_components,
            progress_callback=progress_callback,
            file_io=file_io,
        )
