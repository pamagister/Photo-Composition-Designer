from configparser import ConfigParser
from pathlib import Path

from snapcalendar.common.ConfigItem import ConfigItem


class Config:
    """Lädt und speichert Konfigurationswerte."""

    def __init__(self, config_file=None):
        # Standardwerte als Liste von ConfigItem-Objekten
        self.config_items = [
            # GENERAL
            ConfigItem("GENERAL", "photoDirectory", "../../images", Path, "Path to the directory containing photos"),
            ConfigItem("GENERAL", "anniversariesConfig", "anniversaries.ini", Path, "Path to anniversaries.ini file"),
            ConfigItem("GENERAL", "locationsConfig", "locations_en.ini", Path, "Path to locations.ini file"),

            # CALENDAR
            ConfigItem("CALENDAR", "useCalendar", True, bool, "True: Calendar elements are generated"),
            ConfigItem("CALENDAR", "language", "en_US", str, "Language for the calendar (e.g., de_DE, en_US)"),
            ConfigItem("CALENDAR", "holidayCountries", "NY", str, "Country/state codes for public holidays"),
            ConfigItem("CALENDAR", "startDate", "30.12.2024", str, "Start date of the calendar"),

            # COLORS
            ConfigItem("COLORS", "backgroundColor", (20, 20, 20), tuple, "Background color (RGB)"),
            ConfigItem("COLORS", "textColor1", (255, 255, 255), tuple, "Primary text color"),
            ConfigItem("COLORS", "textColor2", (150, 150, 150), tuple, "Secondary text color"),
            ConfigItem("COLORS", "holidayColor", (255, 0, 0), tuple, "Color for holidays"),

            # GEO
            ConfigItem("GEO", "usePhotoLocationMaps", True, bool, "Use GPS data to generate maps"),
            ConfigItem("GEO", "minimalExtension", 7, int, "Minimum range for map display (degrees)"),

            # SIZE
            ConfigItem("SIZE", "width", 210, int, "Width of the collage in mm"),
            ConfigItem("SIZE", "height", 148, int, "Height of the collage in mm"),
            ConfigItem("SIZE", "calendarHeight", 25, int, "Height of the calendar area in mm"),
            ConfigItem("SIZE", "mapWidth", 30, int, "Width of the locations map in mm"),
            ConfigItem("SIZE", "mapHeight", 30, int, "Height of the locations map in mm"),
            ConfigItem("SIZE", "dpi", 150, int, "Resolution of the image in dpi"),
            ConfigItem("SIZE", "jpgQuality", 80, int, "JPG compression quality (1-100)"),

            # LAYOUT
            ConfigItem("LAYOUT", "fontSizeLarge", 0.4, float, "Font size for large text (relative to height)"),
            ConfigItem("LAYOUT", "fontSizeSmall", 0.15, float, "Font size for small text"),
            ConfigItem("LAYOUT", "fontSizeAnniversaries", 0.10, float, "Font size for anniversaries"),
            ConfigItem("LAYOUT", "marginBottom", 30, int, "Bottom margin in pixels"),
            ConfigItem("LAYOUT", "marginSides", 10, int, "Side margins in pixels"),
            ConfigItem("LAYOUT", "spacing", 10, int, "Spacing between elements"),
            ConfigItem("LAYOUT", "useShortDayNames", True, bool, "Use short weekday names (e.g., Mon, Tue)"),
            ConfigItem("LAYOUT", "useShortMonthNames", True, bool, "Use short month names (e.g., Jan, Feb)"),
            ConfigItem("LAYOUT", "usePhotoDescription", True, bool, "Include photo descriptions in the collage"),
        ]

        # Wenn eine Konfigurationsdatei existiert, laden wir sie
        self.config_parser = ConfigParser()
        if config_file and Path(config_file).exists():
            self.config_parser.read(config_file, encoding="utf-8")

        # Die Werte aus dem File oder die Standardwerte übernehmen
        for item in self.config_items:
            setattr(self, item.key, item.get_value(self.config_parser))

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

    def __str__(self):
        """String-Repräsentation der Konfiguration für Debugging."""
        return "\n".join([f"{item.category}.{item.key} = {getattr(self, item.key)}" for item in self.config_items])


if __name__ == "__main__":
    cfg = Config()
    cfg.write_config(config_file="../config/config.ini")
    print("Config-Datei wurde erstellt")

    #cfg_file = "../config/config.ini"
    #cfg_fromfile = Config(config_file=cfg_file)
    #print("Config-Datei wurde gelesen")

