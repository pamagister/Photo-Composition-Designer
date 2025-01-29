from configparser import ConfigParser
from datetime import datetime
from pathlib import Path


class Config:
    """
    Configuration class for loading and managing settings from an INI file.
    """

    def __init__(self, config_file=None):
        base_path = Path(__file__).parent.parent
        if not config_file:
            config_file = base_path / "config.ini"

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

        # Load the preprocessed configuration
        self.config = ConfigParser()
        self.config.read_string(preprocessed_config)

        # General settings
        photoDir = self.config.get("GENERAL", "photoDirectory")
        self.photoDirectory = (base_path / Path(photoDir)).resolve()

        _startDate = self.config.get("CALENDAR", "startDate")
        self.startDate = self._parse_start_date(_startDate)

        # Calendar settings
        self.useCalendar = self.config.getboolean("CALENDAR", "useCalendar")
        self.language = self.config.get("CALENDAR", "language")
        self.holidayCountries = [
            x.strip()
            for x in self.config.get("CALENDAR", "holidayCountries", fallback="").split(",")
            if x.strip()
        ]

        # Color settings
        self.backgroundColor = self._parse_color(self.config.get("COLORS", "backgroundColor"))
        self.textColor1 = self._parse_color(self.config.get("COLORS", "textColor1"))
        self.textColor2 = self._parse_color(self.config.get("COLORS", "textColor2"))
        self.holidayColor = self._parse_color(self.config.get("COLORS", "holidayColor"))

        # Geo settings
        self.usePhotoLocationMaps = self.config.getboolean("GEO", "usePhotoLocationMaps")
        self.minimalExtension = self.config.getfloat("GEO", "minimalExtension")

        # Size settings
        self.width = self.config.getint("SIZE", "width")
        self.height = self.config.getint("SIZE", "height")
        self.calendarHeight = self.config.getint("SIZE", "calendarHeight")
        self.mapWidth = self.config.getint("SIZE", "mapWidth")
        self.mapHeight = self.config.getint("SIZE", "mapHeight")
        self.jpgQuality = self.config.getint("SIZE", "jpgQuality")

        # Layout settings
        self.fontSizeLarge = self.config.getfloat("LAYOUT", "fontSizeLarge") * self.calendarHeight
        self.fontSizeSmall = self.config.getfloat("LAYOUT", "fontSizeSmall") * self.calendarHeight
        self.fontSizeAnniversaries = (
            self.config.getfloat("LAYOUT", "fontSizeAnniversaries") * self.calendarHeight
        )
        self.marginBottom = self.config.getint("LAYOUT", "marginBottom")
        self.marginSides = self.config.getint("LAYOUT", "marginSides")
        self.spacing = self.config.getint("LAYOUT", "spacing")
        self.useShortDayNames = self.config.getboolean("LAYOUT", "useShortDayNames")
        self.useShortMonthNames = self.config.getboolean("LAYOUT", "useShortMonthNames")
        self.usePhotoDescription = self.config.getboolean("LAYOUT", "usePhotoDescription")

    def _parse_start_date(self, start_date):
        """
        Parses the start date from the INI file and returns it as a datetime object.
        Supports multiple formats: dd.mm.yy, dd.mm.yyyy, dd-mm-yy, dd-mm-yyyy.

        Args:
            start_date (str): Date string from the configuration.

        Returns:
            datetime: Parsed start date.

        Raises:
            ValueError: If the date format is not valid.
        """
        date_formats = ["%d.%m.%y", "%d.%m.%Y", "%d-%m-%y", "%d-%m-%Y"]  # Supported formats
        parsed_date = None
        for date_format in date_formats:
            try:
                parsed_date = datetime.strptime(start_date, date_format)
                break
            except ValueError:
                continue  # Try the next format

        if parsed_date is None:
            raise ValueError(
                f"Invalid date in the 'startDate' field: {start_date}. "
                f"Supported formats: {', '.join(date_formats)}"
            )
        return parsed_date

    def _parse_color(self, color_string):
        """
        Parses a comma-separated RGB color string into a tuple of integers.

        Args:
            color_string (str): Color in the format "R,G,B".

        Returns:
            tuple: RGB color as a tuple of integers.

        Raises:
            ValueError: If the color format is invalid.
        """
        try:
            return tuple(map(int, color_string.split(",")))
        except ValueError:
            raise ValueError(f"Invalid color format: {color_string}. Expected format: R,G,B")

    def __str__(self):
        """
        Returns a string representation of the configuration object for debugging purposes.
        """
        return str(self.__dict__)


if __name__ == "__main__":
    cfg = Config()
    print(cfg)
