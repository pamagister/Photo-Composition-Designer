from configparser import ConfigParser

class Config:
    def __init__(self, config_file="config.ini"):
        self.config = ConfigParser()
        self.config.read(config_file)

        # General settings
        self.width = self.config.getint("GENERAL", "width")
        self.height = self.config.getint("GENERAL", "height")
        self.calendarHeight = self.config.getint("GENERAL", "calendarHeight")
        self.year = self.config.getint("GENERAL", "year")
        self.backgroundColor = tuple(map(int, self.config.get("GENERAL", "backgroundColor").split(",")))
        self.textColor1 = tuple(map(int, self.config.get("GENERAL", "textColor1").split(",")))
        self.textColor2 = tuple(map(int, self.config.get("GENERAL", "textColor2").split(",")))
        self.holidayColor = tuple(map(int, self.config.get("GENERAL", "holidayColor").split(",")))
        self.language = self.config.get("GENERAL", "language")
        self.holidayCountries = [x.strip() for x in self.config.get("GENERAL", "holidayCountries", fallback="").split(",")
                                if x.strip()]

        # Layout settings
        self.fontSizeLarge = self.config.getfloat("LAYOUT", "fontSizeLarge") * self.calendarHeight
        self.fontSizeSmall = self.config.getfloat("LAYOUT", "fontSizeSmall") * self.calendarHeight
        self.fontSizeHoliday = self.config.getfloat("LAYOUT", "fontSizeHoliday") * self.calendarHeight
        self.marginBottom = self.config.getint("LAYOUT", "marginBottom")
        self.marginSides = self.config.getint("LAYOUT", "marginSides")
        self.spacing = self.config.getint("LAYOUT", "spacing")
        self.shortDayNames = self.config.getboolean("LAYOUT", "shortDayNames")
        self.shortMonthNames = self.config.getboolean("LAYOUT", "shortMonthNames")

    def __repr__(self):
        return f"Config({self.__dict__})"