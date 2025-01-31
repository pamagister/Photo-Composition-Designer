from datetime import datetime
from pathlib import Path


class ConfigItem:
    """
    Represents a configuration option with type information and description.
    """

    def __init__(self, category, key, value, value_type, description):
        self.category = category
        self.key = key
        self.value = value
        self.value_type = value_type
        self.description = description

    def get_value(self, config_parser):
        """
        Reads the value from the configuration file and converts it to the specified type.
        If the file does not exist, the default value is used.
        """
        try:
            if self.value_type == bool:
                return config_parser.getboolean(self.category, self.key, fallback=self.value)
            elif self.value_type == int:
                return config_parser.getint(self.category, self.key, fallback=self.value)
            elif self.value_type == float:
                return config_parser.getfloat(self.category, self.key, fallback=self.value)
            elif self.value_type == Path:
                path_str = config_parser.get(self.category, self.key, fallback=str(self.value))
                return Path(path_str).resolve()  # Relativ zu Absolut
            elif self.value_type == datetime:
                date_str = config_parser.get(self.category, self.key, fallback=self.value)
                return self._parse_start_date(date_str)
            elif self.value_type == tuple:  # RGB-Farbwerte als Tupel (R,G,B)
                color_str = config_parser.get(self.category, self.key, fallback=self.value)
                return self._parse_tuple(color_str)
            else:
                return config_parser.get(self.category, self.key, fallback=self.value)
        except Exception as e:
            raise ValueError(f"Fehler beim Parsen von {self.key}: {e}")

    @staticmethod
    def _parse_start_date(start_date):
        """Converts the date from the config file into a `datetime` object."""
        date_formats = ["%d.%m.%y", "%d.%m.%Y", "%d-%m-%y", "%d-%m-%Y"]
        for fmt in date_formats:
            try:
                return datetime.strptime(start_date, fmt)
            except ValueError:
                continue
        raise ValueError(f"Invalid date: {start_date}. Permitted formats: {', '.join(date_formats)}")

    @staticmethod
    def _parse_tuple(tupleValue: str|tuple):
        """Converts a character string in the format `R,G,B` into a tuple `(R, G, B)`."""
        if isinstance(tupleValue, tuple):
            return tupleValue
        try:
            return tuple(map(int, tupleValue.split(",")))
        except ValueError:
            raise ValueError(f"Invalid color format: {tupleValue}. Expected format: R,G,B")

    def format_value(self):
        """Outputs the value as a string for the config file."""
        if isinstance(self.value, bool):
            return "True" if self.value else "False"
        if isinstance(self.value, tuple):
            return ",".join(map(str, self.value))
        return str(self.value)
