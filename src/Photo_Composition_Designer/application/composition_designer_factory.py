"""Factory for creating composition designers at application boundaries."""

from __future__ import annotations

from collections.abc import Callable
from logging import Logger

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.base import CompositionDesigner

ProgressCallback = Callable[[int, int], None]


class CompositionDesignerFactory:
    """Create composition designers with consistent application dependencies."""

    def create(
        self,
        config: ConfigParameterManager,
        logger: Logger,
        progress_callback: ProgressCallback | None = None,
    ) -> CompositionDesigner:
        """Create a designer configured for one composition workflow."""
        return CompositionDesigner(
            config,
            logger,
            progress_callback=progress_callback,
        )
