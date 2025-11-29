"""CLI interface for Photo-Composition-Designer using the generic config framework.

This file uses the CliGenerator from the generic config framework.
"""

import os.path

from config_cli_gui.cli import CliGenerator

from Photo_Composition_Designer.common.logging import initialize_logging
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.base import CompositionDesigner


def validate_config(config_manager: ConfigParameterManager) -> bool:
    """Validate the configuration parameters.

    Args:
        config_manager: Configuration manager instance
        logger: Logger instance for error reporting

    Returns:
        True if configuration is valid, False otherwise
    """
    # Initialize logging system
    logger_manager = initialize_logging(config_manager)
    logger = logger_manager.get_logger("Photo_Composition_Designer.cli")

    # Get CLI category and check required parameters
    cli_parameters = config_manager.get_cli_parameters()
    if not cli_parameters:
        logger.error("No CLI configuration found")

    for param in cli_parameters:
        if param.name == "photoDirectory":
            photo_dir = param.value
            if os.path.exists(photo_dir):
                logger.debug(f"Input file validation passed: {photo_dir}")
                return True
            else:
                logger.debug(f"Input file not found: {photo_dir}")

    return False


def run_main_processing(config_manager: ConfigParameterManager) -> int:
    """Main processing function that gets called by the CLI generator.

    Args:
        config_manager: Configuration manager with all settings

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Initialize logging system
    logger_manager = initialize_logging(config_manager)
    logger = logger_manager.get_logger("Photo_Composition_Designer.cli")

    try:
        # Log startup information
        logger.info("Starting Photo_Composition_Designer CLI")
        logger_manager.log_config_summary()

        # Validate configuration
        if not validate_config(config_manager):
            logger.error("Configuration validation failed")
            return 1

        # Create and run Composition Designer
        logger.info("Starting conversion process")
        composition_designer = CompositionDesigner(config_manager)
        composition_designer.generate_compositions_from_folders()
        logger.info("Conversion process completed")

        logger.info("CLI processing completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        logger.debug("Full traceback:", exc_info=True)
        return 1


def main():
    """Main entry point for the CLI application."""
    # Create the base configuration manager
    config_manager = ConfigParameterManager()

    # Create CLI generator
    cli_generator = CliGenerator(
        config_manager=config_manager, app_name="Photo_Composition_Designer"
    )

    # Run the CLI with our main processing function
    return cli_generator.run_cli(
        main_function=run_main_processing,
        description="Process GPX files with various operations like compression, "
        "merging, and POI extraction",
        validator=validate_config,
    )


if __name__ == "__main__":
    import sys

    sys.exit(main())
