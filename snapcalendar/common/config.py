from configparser import ConfigParser
from datetime import datetime
from pathlib import Path


class Config:
    def __init__(self, config_file=None):
        if not config_file:
            base_path = Path(__file__).parent.parent
            config_file = base_path / "config.ini"
        self.config = ConfigParser()
        self.config.read(config_file)

        # General settings
        self.width = self.config.getint("GENERAL", "width")
        self.height = self.config.getint("GENERAL", "height")
        self.calendarHeight = self.config.getint("GENERAL", "calendarHeight")
        _startDate = self.config.get("GENERAL", "startDate")

        self.startDate = self._parse_start_date(_startDate)
        self.backgroundColor = tuple(map(int, self.config.get("GENERAL", "backgroundColor").split(",")))
        self.textColor1 = tuple(map(int, self.config.get("GENERAL", "textColor1").split(",")))
        self.textColor2 = tuple(map(int, self.config.get("GENERAL", "textColor2").split(",")))
        self.holidayColor = tuple(map(int, self.config.get("GENERAL", "holidayColor").split(",")))
        self.language = self.config.get("GENERAL", "language")
        self.holidayCountries = [
            x.strip() for x in self.config.get("GENERAL", "holidayCountries", fallback="").split(",") if x.strip()
        ]
        self.photoDirectory = self.config.get("GENERAL", "photoDirectory")

        # Layout settings
        self.fontSizeLarge = self.config.getfloat("LAYOUT", "fontSizeLarge") * self.calendarHeight
        self.fontSizeSmall = self.config.getfloat("LAYOUT", "fontSizeSmall") * self.calendarHeight
        self.fontSizeAnniversaries = self.config.getfloat("LAYOUT", "fontSizeAnniversaries") * self.calendarHeight
        self.marginBottom = self.config.getint("LAYOUT", "marginBottom")
        self.marginSides = self.config.getint("LAYOUT", "marginSides")
        self.spacing = self.config.getint("LAYOUT", "spacing")
        self.useShortDayNames = self.config.getboolean("LAYOUT", "useShortDayNames")
        self.useShortMonthNames = self.config.getboolean("LAYOUT", "useShortMonthNames")
        self.usePhotoLocationMaps = self.config.getboolean("LAYOUT", "usePhotoLocationMaps")
        self.usePhotoDescription = self.config.getboolean("LAYOUT", "usePhotoDescription")
        self.photoLocationRange = self.config.getfloat("LAYOUT", "photoLocationRange")

    def _parse_start_date(self, startDate):
        date_formats = ["%d.%m.%y", "%d.%m.%Y", "%d-%m-%y", "%d-%m-%Y"]  # Unterstützte Formate
        parsed_date = None
        for date_format in date_formats:
            try:
                parsed_date = datetime.strptime(startDate, date_format)
                break
            except ValueError:
                continue  # Versuche das nächste Format

        if parsed_date is None:
            raise ValueError(
                f"Invalid date in the 'startDate' field: {startDate}. Supported formats: {', '.join(date_formats)}"
            )
        return parsed_date


if __name__ == "__main__":
    cfg = Config()
    print(cfg.__dict__)
