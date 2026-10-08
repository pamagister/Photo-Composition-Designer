"""Application workflows that coordinate domain and rendering components."""

from logging import Logger

from Photo_Composition_Designer.application.composition_designer_factory import (
    CompositionDesignerFactory,
    ProgressCallback,
)
from Photo_Composition_Designer.application.composition_workflow import CompositionWorkflow
from Photo_Composition_Designer.config.config import ConfigParameterManager


class CompositionApplicationFactory:
    """Build composition workflows with a consistent designer factory."""

    def __init__(self, logger: Logger) -> None:
        """Initialize the application factory with its shared logger."""
        self.logger = logger
        self.designer_factory = CompositionDesignerFactory()

    def create_workflow(
        self,
        config: ConfigParameterManager,
        progress_callback: ProgressCallback | None = None,
    ) -> CompositionWorkflow:
        """Create a workflow and its primary designer for the given configuration."""
        designer = self.designer_factory.create(config, self.logger, progress_callback)
        return CompositionWorkflow(
            config,
            self.logger,
            designer,
            designer_factory=self.designer_factory,
        )


__all__ = [
    "CompositionApplicationFactory",
    "CompositionDesignerFactory",
    "CompositionWorkflow",
]
