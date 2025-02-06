from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

from designer.common.ConfigItem import ConfigItem

DEFAULT_CONFIG = [
    # GENERAL
    (
        "GENERAL",
        "photoDirectory",
        "../../images",
        Path,
        "Path to the directory containing photos (absolute, or relative to this config.ini file)",
    ),
    (
        "GENERAL",
        "anniversariesConfig",
        "anniversaries.ini",
        Path,
        "Path to anniversaries.ini file (absolute, or relative to this config.ini file)",
    ),
    (
        "GENERAL",
        "locationsConfig",
        "locations_en.ini",
        Path,
        "Path to locations.ini file (absolute, or relative to this config.ini file)",
    ),
    (
        "GENERAL",
        "compositionTitle",
        "This is the title of the composition",
        str,
        "This is the title of the composition on the first page. Leave empty if not required.",
    ),
    # CALENDAR
    ("CALENDAR", "useCalendar", True, bool, "True: Calendar elements are generated"),
    ("CALENDAR", "language", "de_DE", str, "Language for the calendar (e.g., de_DE, en_US)"),
    (
        "CALENDAR",
        "holidayCountries",
        "SN,BY",
        tuple,
        "Country/state codes for public holidays, e.g. NY,CA See https://pypi.org/project/holidays/",
    ),
    ("CALENDAR", "startDate", "30.12.2024", datetime, "Start date of the calendar"),
    ("CALENDAR", "collagesToGenerate", 53, int, "Number of collages to be generated (e.g. number of weeks)"),
    # COLORS
    ("COLORS", "backgroundColor", (20, 20, 20), tuple, "Background color (RGB)"),
    ("COLORS", "textColor1", (255, 255, 255), tuple, "Primary text color"),
    ("COLORS", "textColor2", (150, 150, 150), tuple, "Secondary text color"),
    ("COLORS", "holidayColor", (255, 0, 0), tuple, "Color for holidays"),
    # GEO
    ("GEO", "usePhotoLocationMaps", True, bool, "Use GPS data to generate maps"),
    ("GEO", "minimalExtension", 7, int, "Minimum range for map display (degrees)"),
    # SIZE
    ("SIZE", "width", 210, int, "Width of the collage in mm"),
    ("SIZE", "height", 148, int, "Height of the collage in mm"),
    ("SIZE", "calendarHeight", 20, int, "Height of the calendar area in mm"),
    ("SIZE", "mapWidth", 20, int, "Width of the locations map in mm"),
    ("SIZE", "mapHeight", 20, int, "Height of the locations map in mm"),
    ("SIZE", "dpi", 150, int, "Resolution of the image in dpi"),
    ("SIZE", "jpgQuality", 80, int, "JPG compression quality (1-100)"),
    # LAYOUT
    ("LAYOUT", "fontSizeLarge", 0.5, float, "Font size for large text"),
    ("LAYOUT", "fontSizeSmall", 0.15, float, "Font size for small text"),
    ("LAYOUT", "fontSizeAnniversaries", 0.115, float, "Font size for anniversaries"),
    ("LAYOUT", "marginBottom", 3, int, "Bottom margin in mm"),
    ("LAYOUT", "marginSides", 3, int, "Side margins in mm"),
    ("LAYOUT", "spacing", 2, int, "Spacing between elements in mm"),
    ("LAYOUT", "useShortDayNames", False, bool, "Use short weekday names (e.g., Mon, Tue)"),
    ("LAYOUT", "useShortMonthNames", True, bool, "Use short month names (e.g., Jan, Feb)"),
    ("LAYOUT", "usePhotoDescription", True, bool, "Include photo descriptions in the collage"),
    ("LAYOUT", "generatePdf", True, bool, "Combine all generated collages into one pdf"),
]


class Config:
    """Lädt und speichert Konfigurationswerte."""

    def __init__(self, config_file=None):
        self._width = 0
        self._height = 0
        self._calendarHeight = 0
        self._mapWidth = 0
        self._mapHeight = 0
        self._marginBottom = 0
        self._marginSides = 0
        self._spacing = 0

        self._fontSizeLarge = 0
        self._fontSizeSmall = 0
        self._fontSizeAnniversaries = 0
        self._config_path = None

        if config_file:
            base_dir = Path(config_file)
        else:
            base_dir = Path(__file__).parent.parent / "config" / "config.ini"
        self._config_path = base_dir

        # Standardwerte als Liste von ConfigItem-Objekten
        self.config_items: list[ConfigItem] = [ConfigItem(*item, base_dir=base_dir) for item in DEFAULT_CONFIG]
        self.config_parser = ConfigParser()

        for item in self.config_items:
            setattr(self, item.key, item.get_value(self.config_parser))

        self._save_original_values()

        # If a configuration file exists, we load it
        if config_file and Path(config_file).exists():
            self.update_default_values(Path(config_file))
        self._calculate_attributes_from_original()

    def _save_original_values(self):
        # size values (pixels vs. mm)
        self._width = self.width
        self._height = self.height
        self._calendarHeight = self.calendarHeight
        self._mapWidth = self.mapWidth
        self._mapHeight = self.mapHeight
        self._marginBottom = self.marginBottom
        self._marginSides = self.marginSides
        self._spacing = self.spacing
        # font size (relative vs. absolute)
        self._fontSizeLarge = self.fontSizeLarge
        self._fontSizeSmall = self.fontSizeSmall
        self._fontSizeAnniversaries = self.fontSizeAnniversaries

    def _calculate_attributes_from_original(self):
        # Conversion to the desired size
        self.width = int(self._width * self.dpi / 25.4)
        self.height = int(self._height * self.dpi / 25.4)
        self.calendarHeight = int(self._calendarHeight * self.dpi / 25.4)
        self.mapWidth = int(self._mapWidth * self.dpi / 25.4)
        self.mapHeight = int(self._mapHeight * self.dpi / 25.4)
        self.marginBottom = int(self._marginBottom * self.dpi / 25.4)
        self.marginSides = int(self._marginSides * self.dpi / 25.4)
        self.spacing = int(self._spacing * self.dpi / 25.4)

        self.fontSizeLarge = self._fontSizeLarge * self.calendarHeight
        self.fontSizeSmall = self._fontSizeSmall * self.calendarHeight
        self.fontSizeAnniversaries = self._fontSizeAnniversaries * self.calendarHeight

    def update_default_values(self, config_file: Path):
        # Preprocess the config file to remove comments and strip whitespace
        processed_lines = []
        with open(config_file, "r", encoding="utf-8") as file:
            for line in file:
                # Remove everything after the first ";" (comments)
                line = line.split(";", 1)[0].strip()
                if line:  # Skip empty lines
                    processed_lines.append(line)

        # Create a temporary string to load into ConfigParser
        preprocessed_config = "\n".join(processed_lines)
        file_config_parser = ConfigParser()
        file_config_parser.read_string(preprocessed_config)
        base_path = config_file
        for item in self.config_items:
            item.set_base_path(base_path)
            setattr(self, item.key, item.get_value(file_config_parser))
        self._save_original_values()
        self._calculate_attributes_from_original()

    def write_config(self, config_file="../config/config.ini"):
        """Schreibt die aktuelle Konfiguration in eine Datei."""
        config_parser = ConfigParser()

        for item in self.config_items:
            if item.category not in config_parser:
                config_parser[item.category] = {}

            config_parser[item.category][item.key] = item.format_value()

        # Konfigurationsdatei mit Kommentaren schreiben
        with open(config_file, "w", encoding="utf-8") as file:
            for section in config_parser.sections():
                file.write(f"[{section}]\n")
                for item in self.config_items:
                    if item.category == section:
                        key_value = f"{item.key} = {config_parser[section][item.key]}"
                        comment = f"; {item.description}"
                        file.write(f"{key_value.ljust(35)} {comment}\n")
                file.write("\n")

    def update_config_items(self):
        """writes the values of the current object to the raw values in config_items"""
        for itemIndex, item in enumerate(self.config_items):
            value = getattr(self, item.key)
            self.config_items[itemIndex].value = value

    def get_config_path(self):
        return self._config_path

    def __str__(self):
        """String-Repräsentation der Konfiguration für Debugging."""
        return "\n".join([f"{item.category}.{item.key} = {getattr(self, item.key)}" for item in self.config_items])


if __name__ == "__main__":
    # write default values to config
    cfg = Config()
    cfg.write_config(config_file="../config/config.ini")

    cfg_file_name = "config_update.ini"

    project_base_path = Path(__file__).parent.parent
    cfg_file = project_base_path / "config" / cfg_file_name
    cfg_fromfile = Config(cfg_file)
    print(cfg_fromfile)
