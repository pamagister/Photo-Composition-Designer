from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

from designer.common.ConfigItem import ConfigItem


class Config:
    """Lädt und speichert Konfigurationswerte."""

    def __init__(self, config_file=None):
        # Vermeidet Rekursion in __setattr__
        super().__setattr__("_config_items", {})

        if config_file:
            base_dir = Path(config_file)
        else:
            base_dir = Path(__file__).parent.parent / "config" / "config.ini"
        self._config_path = base_dir

        # GENERAL
        self.photoDirectory = ConfigItem(
            "GENERAL",
            "photoDirectory",
            "../../images",
            Path,
            "Path to the directory containing photos (absolute, or relative to this config.ini file)",
        )
        self.anniversariesConfig = ConfigItem(
            "GENERAL",
            "anniversariesConfig",
            "anniversaries.ini",
            Path,
            "Path to anniversaries.ini file (absolute, or relative to this config.ini file)",
        )
        self.locationsConfig = ConfigItem(
            "GENERAL",
            "locationsConfig",
            "locations_en.ini",
            Path,
            "Path to locations.ini file (absolute, or relative to this config.ini file)",
        )
        self.compositionTitle = ConfigItem(
            "GENERAL",
            "compositionTitle",
            "This is the title of the composition",
            str,
            "This is the title of the composition on the first page. Leave empty if not required.",
        )

        # CALENDAR
        self.useCalendar = ConfigItem("CALENDAR", "useCalendar", True, bool, "True: Calendar elements are generated")
        self.language = ConfigItem(
            "CALENDAR", "language", "de_DE", str, "Language for the calendar (e.g., de_DE, en_US)"
        )
        self.holidayCountries = ConfigItem(
            "CALENDAR",
            "holidayCountries",
            "SN",
            tuple,
            "Country/state codes for public holidays, e.g. NY,CA See https://pypi.org/project/holidays/",
        )
        self.startDate = ConfigItem("CALENDAR", "startDate", "30.12.2024", datetime, "Start date of the calendar")
        self.collagesToGenerate = ConfigItem(
            "CALENDAR", "collagesToGenerate", 11, int, "Number of collages to be generated (e.g. number of weeks)"
        )

        # COLORS
        self.backgroundColor = ConfigItem("COLORS", "backgroundColor", (20, 20, 20), tuple, "Background color (RGB)")
        self.textColor1 = ConfigItem("COLORS", "textColor1", (255, 255, 255), tuple, "Primary text color")
        self.textColor2 = ConfigItem("COLORS", "textColor2", (150, 150, 150), tuple, "Secondary text color")
        self.holidayColor = ConfigItem("COLORS", "holidayColor", (255, 0, 0), tuple, "Color for holidays")

        # GEO
        self.usePhotoLocationMaps = ConfigItem(
            "GEO", "usePhotoLocationMaps", True, bool, "Use GPS data to generate maps"
        )
        self.minimalExtension = ConfigItem("GEO", "minimalExtension", 7, int, "Minimum range for map display (degrees)")

        # SIZE
        self.width = ConfigItem("SIZE", "width", 216, int, "Width of the collage in mm")
        self.height = ConfigItem("SIZE", "height", 154, int, "Height of the collage in mm")
        self.calendarHeight = ConfigItem("SIZE", "calendarHeight", 18, int, "Height of the calendar area in mm")
        self.mapWidth = ConfigItem("SIZE", "mapWidth", 20, int, "Width of the locations map in mm")
        self.mapHeight = ConfigItem("SIZE", "mapHeight", 20, int, "Height of the locations map in mm")
        self.dpi = ConfigItem("SIZE", "dpi", 150, int, "Resolution of the image in dpi")
        self.jpgQuality = ConfigItem("SIZE", "jpgQuality", 90, int, "JPG compression quality (1-100)")

        # LAYOUT
        self.fontSizeLarge = ConfigItem("LAYOUT", "fontSizeLarge", 0.5, float, "Font size for large text")
        self.fontSizeSmall = ConfigItem("LAYOUT", "fontSizeSmall", 0.14, float, "Font size for small text")
        self.fontSizeAnniversaries = ConfigItem(
            "LAYOUT", "fontSizeAnniversaries", 0.115, float, "Font size for anniversaries"
        )
        self.marginBottom = ConfigItem("LAYOUT", "marginBottom", 3, int, "Bottom margin in mm")
        self.marginSides = ConfigItem("LAYOUT", "marginSides", 3, int, "Side margins in mm")
        self.spacing = ConfigItem("LAYOUT", "spacing", 2, int, "Spacing between elements in mm")
        self.useShortDayNames = ConfigItem(
            "LAYOUT", "useShortDayNames", False, bool, "Use short weekday names (e.g., Mon, Tue)"
        )
        self.useShortMonthNames = ConfigItem(
            "LAYOUT", "useShortMonthNames", True, bool, "Use short month names (e.g., Jan, Feb)"
        )
        self.usePhotoDescription = ConfigItem(
            "LAYOUT", "usePhotoDescription", True, bool, "Include photo descriptions in the collage"
        )
        self.generatePdf = ConfigItem(
            "LAYOUT", "generatePdf", True, bool, "Combine all generated collages into one pdf"
        )

        # If a configuration file exists, we load it
        if config_file and Path(config_file).exists():
            self.update_default_values(Path(config_file))

    def __setattr__(self, key, value):
        """Falls key ein ConfigItem ist, speichere den Wert, sonst setze das Attribut normal."""
        if key in self.__dict__ and isinstance(self.__dict__[key], ConfigItem):
            self.__dict__[key].value = value  # Direkt den Wert setzen
        else:
            super().__setattr__(key, value)

    def __getattribute__(self, key, default=False):
        """Gibt den Wert eines ConfigItems zurück, falls es existiert."""
        obj = super().__getattribute__(key)
        if isinstance(obj, ConfigItem) and not default:
            return obj.value  # Direkt den gespeicherten Wert zurückgeben
        return obj

    def xx_calculate_attributes_from_original(self):
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
        """Lädt Werte aus einer Config-Datei und überschreibt die Standardwerte."""

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

        # Set base path for potential relative paths
        base_path = config_file

        for attr_name in dir(self):
            # Prüfe, ob das Attribut ein ConfigItem ist
            attr_value = super().__getattribute__(attr_name)
            if isinstance(attr_value, ConfigItem):
                if file_config_parser.has_section(attr_value.category):
                    new_value = file_config_parser.get(attr_value.category, attr_value.key)
                    super().__setattr__(attr_value.key, new_value)

    def write_config(self, config_file="../config/config.ini"):
        """Schreibt die aktuelle Konfiguration in eine Datei."""
        config_parser = ConfigParser()

        # Alle Attribute der Klasse durchlaufen und nach ConfigItem filtern
        for attr_name in dir(self):
            attr_value = super().__getattribute__(attr_name)  # Umgeht __getattribute__

            if isinstance(attr_value, ConfigItem):
                if attr_value.category not in config_parser:
                    config_parser[attr_value.category] = {}

                config_parser[attr_value.category][attr_value.key] = attr_value.format_value()

        # Konfigurationsdatei mit Kommentaren schreiben
        with open(config_file, "w", encoding="utf-8") as file:
            for section in config_parser.sections():
                file.write(f"[{section}]\n")
                for attr_name in dir(self):
                    attr_value = super().__getattribute__(attr_name)  # Umgeht __getattribute__
                    if isinstance(attr_value, ConfigItem) and attr_value.category == section:
                        key_value = f"{attr_value.key} = {config_parser[section][attr_value.key]}"
                        comment = f"; {attr_value.description}"
                        file.write(f"{key_value.ljust(35)} {comment}\n")
                file.write("\n")

    def update_config_items(self):
        """writes the values of the current object to the raw values in config_items"""
        for itemIndex, item in enumerate(self.config_items):
            value = getattr(self, item.key)
            self.config_items[itemIndex].value = value

    def get_config_path(self):
        return self._config_path


if __name__ == "__main__":
    # write default values to config
    cfg = Config()
    cfg.write_config(config_file="../config/config.ini")

    cfg_file_name = "config2.ini"

    project_base_path = Path(__file__).parent.parent
    cfg_file = project_base_path / "config" / cfg_file_name
    cfg_fromfile = Config(cfg_file)
    print(cfg_fromfile)

