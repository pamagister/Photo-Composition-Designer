"""
Central configuration management for the new project.

This module provides a single source of truth for all configuration parameters
organized in categories (GENERAL, CALENDAR, COLORS, GEO, SIZE, LAYOUT).
It can generate config files, CLI modules, and documentation from the parameter definitions.
"""

from datetime import datetime
from pathlib import Path

from config_cli_gui.config import Color, ConfigCategory, ConfigManager, ConfigParameter
from config_cli_gui.docs import DocumentationGenerator


class AppConfig(ConfigCategory):
    """Application-specific configuration parameters."""

    def get_category_name(self) -> str:
        return "app"

    log_level: ConfigParameter = ConfigParameter(
        name="log_level",
        value="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level for the application",
    )


class GeneralConfig(ConfigCategory):
    """GENERAL configuration parameters."""

    def get_category_name(self) -> str:
        return "general"

    photoDirectory: ConfigParameter = ConfigParameter(
        name="photoDirectory",
        value=Path("../../images"),
        help="Path to the directory containing photos "
        "(absolute, or relative to this config.ini file)",
        is_cli=True,
        required=False,
    )

    anniversariesConfig: ConfigParameter = ConfigParameter(
        name="anniversariesConfig",
        value=Path("anniversaries.ini"),
        help="Path to anniversaries.ini file (absolute, or relative to this config.ini file)",
    )

    locationsConfig: ConfigParameter = ConfigParameter(
        name="locationsConfig",
        value=Path("locations_en.ini"),
        help="Path to locations.ini file (absolute, or relative to this config.ini file)",
    )

    compositionTitle: ConfigParameter = ConfigParameter(
        name="compositionTitle",
        value="This is the title of the composition",
        help="This is the title of the composition on the first page. Leave empty if not required.",
    )


class CalendarConfig(ConfigCategory):
    """CALENDAR configuration parameters."""

    def get_category_name(self) -> str:
        return "calendar"

    useCalendar: ConfigParameter = ConfigParameter(
        name="useCalendar",
        value=True,
        help="True: Calendar elements are generated",
    )

    language: ConfigParameter = ConfigParameter(
        name="language",
        value="de_DE",
        help="Language for the calendar (e.g., de_DE, en_US)",
    )

    holidayCountries: ConfigParameter = ConfigParameter(
        name="holidayCountries",
        value="SN",
        help="Country/state codes for public holidays, e.g., NY,CA",
    )

    startDate: ConfigParameter = ConfigParameter(
        name="startDate",
        value=datetime.fromisoformat("2025-12-31"),
        help="Start date of the calendar",
        is_cli=True,
    )

    collagesToGenerate: ConfigParameter = ConfigParameter(
        name="collagesToGenerate",
        value=5,
        help="Number of collages to be generated (e.g. number of weeks)",
    )


class ColorsConfig(ConfigCategory):
    """COLORS configuration parameters."""

    def get_category_name(self) -> str:
        return "colors"

    backgroundColor: ConfigParameter = ConfigParameter(
        name="backgroundColor",
        value=Color(20, 20, 20),
        help="Background color (RGB)",
    )

    textColor1: ConfigParameter = ConfigParameter(
        name="textColor1",
        value=Color(255, 255, 255),
        help="Primary text color",
    )

    textColor2: ConfigParameter = ConfigParameter(
        name="textColor2",
        value=Color(150, 150, 150),
        help="Secondary text color",
    )

    holidayColor: ConfigParameter = ConfigParameter(
        name="holidayColor",
        value=Color(255, 0, 0),
        help="Color for holidays",
    )


class GeoConfig(ConfigCategory):
    """GEO configuration parameters."""

    def get_category_name(self) -> str:
        return "geo"

    usePhotoLocationMaps: ConfigParameter = ConfigParameter(
        name="usePhotoLocationMaps",
        value=True,
        help="Use GPS data to generate maps",
    )

    minimalExtension: ConfigParameter = ConfigParameter(
        name="minimalExtension",
        value=7,
        help="Minimum range for map display (degrees)",
    )


class SizeConfig(ConfigCategory):
    """SIZE configuration parameters."""

    def get_category_name(self) -> str:
        return "size"

    width: ConfigParameter = ConfigParameter(
        name="width",
        value=216,
        help="Width of the collage in mm",
        is_cli=True,
    )

    height: ConfigParameter = ConfigParameter(
        name="height",
        value=154,
        help="Height of the collage in mm",
        is_cli=True,
    )

    calendarHeight: ConfigParameter = ConfigParameter(
        name="calendarHeight",
        value=18,
        help="Height of the calendar area in mm",
    )

    mapWidth: ConfigParameter = ConfigParameter(
        name="mapWidth",
        value=20,
        help="Width of the locations map in mm",
    )

    mapHeight: ConfigParameter = ConfigParameter(
        name="mapHeight",
        value=20,
        help="Height of the locations map in mm",
    )

    dpi: ConfigParameter = ConfigParameter(
        name="dpi",
        value=100,
        help="Resolution of the image in dpi",
    )

    jpgQuality: ConfigParameter = ConfigParameter(
        name="jpgQuality",
        value=90,
        help="JPG compression quality (1-100)",
    )


class LayoutConfig(ConfigCategory):
    """LAYOUT configuration parameters."""

    def get_category_name(self) -> str:
        return "layout"

    fontSizeLarge: ConfigParameter = ConfigParameter(
        name="fontSizeLarge",
        value=0.5,
        help="Font size for large text",
    )

    fontSizeSmall: ConfigParameter = ConfigParameter(
        name="fontSizeSmall",
        value=0.14,
        help="Font size for small text",
    )

    fontSizeAnniversaries: ConfigParameter = ConfigParameter(
        name="fontSizeAnniversaries",
        value=0.115,
        help="Font size for anniversaries",
    )

    marginTop: ConfigParameter = ConfigParameter(
        name="marginTop",
        value=6,
        help="Top margin in mm",
    )

    marginBottom: ConfigParameter = ConfigParameter(
        name="marginBottom",
        value=3,
        help="Bottom margin in mm",
    )

    marginSides: ConfigParameter = ConfigParameter(
        name="marginSides",
        value=3,
        help="Side margins in mm",
    )

    spacing: ConfigParameter = ConfigParameter(
        name="spacing",
        value=2,
        help="Spacing between elements in mm",
    )

    useShortDayNames: ConfigParameter = ConfigParameter(
        name="useShortDayNames",
        value=False,
        help="Use short weekday names (e.g., Mon, Tue)",
    )

    useShortMonthNames: ConfigParameter = ConfigParameter(
        name="useShortMonthNames",
        value=True,
        help="Use short month names (e.g., Jan, Feb)",
    )

    usePhotoDescription: ConfigParameter = ConfigParameter(
        name="usePhotoDescription",
        value=True,
        help="Include photo descriptions in the collage",
    )

    generatePdf: ConfigParameter = ConfigParameter(
        name="generatePdf",
        value=True,
        help="Combine all generated collages into one pdf",
    )


class ConfigParameterManager(ConfigManager):
    """Main configuration manager that handles all parameter categories."""

    app: AppConfig
    general: GeneralConfig
    calendar: CalendarConfig
    colors: ColorsConfig
    geo: GeoConfig
    size: SizeConfig
    layout: LayoutConfig

    def __init__(self, config_file: str | None = None, **kwargs):
        categories = (
            AppConfig(),
            GeneralConfig(),
            CalendarConfig(),
            ColorsConfig(),
            GeoConfig(),
            SizeConfig(),
            LayoutConfig(),
        )
        super().__init__(categories, config_file, **kwargs)


def main():
    """Main function to generate config file and documentation."""
    default_config: str = "config.yaml"
    default_cli_doc: str = "docs/usage/cli.md"
    default_config_doc: str = "docs/usage/config.md"

    config_manager = ConfigParameterManager()
    docGen = DocumentationGenerator(config_manager)

    docGen.generate_default_config_file(output_file=default_config)
    print(f"Generated: {default_config}")

    docGen.generate_config_markdown_doc(output_file=default_config_doc)
    print(f"Generated: {default_config_doc}")

    docGen.generate_cli_markdown_doc(output_file=default_cli_doc)
    print(f"Generated: {default_cli_doc}")


if __name__ == "__main__":
    main()
