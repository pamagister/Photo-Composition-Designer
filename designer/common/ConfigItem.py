from datetime import datetime
from pathlib import Path


class ConfigItem:
    """
    Represents a configuration option with type information and description.
    """

    def __init__(self, category, key, value, value_type, description, base_dir=None):
        self.category = category
        self.key = key
        self.value = value
        self.value_type = value_type
        self.description = description
        self.config_base_path = base_dir

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
                return self._resolve_path(path_str)
            elif self.value_type == datetime:
                date_str = config_parser.get(self.category, self.key, fallback=self.value)
                return self._parse_start_date(date_str)
            elif self.value_type == tuple:  # RGB-Farbwerte als Tupel (R,G,B)
                tuple_string = config_parser.get(self.category, self.key, fallback=self.value)
                return self._parse_tuple(tuple_string)
            else:
                return config_parser.get(self.category, self.key, fallback=self.value)
        except Exception as e:
            raise ValueError(f"Fehler beim Parsen von {self.key}: {e}")

    def set_base_path(self, path_str):
        self.config_base_path = Path(path_str)

    def _resolve_path(self, path_str):
        if self.config_base_path:
            resolved_path = (
                Path(path_str) if Path(path_str).is_absolute() else self.config_base_path.parent / Path(path_str)
            ).resolve()
        else:
            resolved_path = self.config_base_path = Path(path_str).resolve()

        return resolved_path

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
    def _parse_tuple(tupleValue: str | tuple):
        """Converts a string of multiple values (string or int) `value1,value2,value3` into a tuple `(value1, value2, value3)`.

        Supports both integers and strings as elements.
        """
        if isinstance(tupleValue, tuple):
            return tupleValue  # If already a tuple, return directly

        try:
            # Try to parse the values as integer or string
            return tuple(int(v) if v.strip().isdigit() else v.strip() for v in tupleValue.split(","))
        except Exception:
            raise ValueError(f"Invalid tuple format: {tupleValue}. Expected format: value1, value2, ...")

    def format_value(self):
        """Outputs the value as a string for the config file."""
        if isinstance(self.value, bool):
            return "True" if self.value else "False"
        if isinstance(self.value, tuple):
            return ",".join(map(str, self.value))
        return str(self.value)
