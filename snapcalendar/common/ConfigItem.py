from configparser import ConfigParser
from datetime import datetime
from pathlib import Path


class ConfigItem:
    """
    Repräsentiert eine Konfigurationsoption mit Typ-Information und Beschreibung.
    """

    def __init__(self, category, key, value, value_type, description):
        self.category = category
        self.key = key
        self.value = value
        self.value_type = value_type
        self.description = description

    def get_value(self, config_parser):
        """
        Liest den Wert aus der Konfigurationsdatei und wandelt ihn in den angegebenen Typ um.
        Falls die Datei nicht existiert, wird der Standardwert verwendet.
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
                return color_str
                return self._parse_color(color_str)
            else:
                return config_parser.get(self.category, self.key, fallback=self.value)
        except Exception as e:
            raise ValueError(f"Fehler beim Parsen von {self.key}: {e}")

    @staticmethod
    def _parse_start_date(start_date):
        """ Konvertiert das Datum aus der Config-Datei in ein `datetime`-Objekt. """
        date_formats = ["%d.%m.%y", "%d.%m.%Y", "%d-%m-%y", "%d-%m-%Y"]
        for fmt in date_formats:
            try:
                return datetime.strptime(start_date, fmt)
            except ValueError:
                continue
        raise ValueError(f"Ungültiges Datum: {start_date}. Erlaubte Formate: {', '.join(date_formats)}")

    @staticmethod
    def _parse_color(color_string):
        """ Wandelt eine Zeichenfolge im Format `R,G,B` in ein Tupel `(R, G, B)` um. """
        try:
            return tuple(map(int, color_string.split(",")))
        except ValueError:
            raise ValueError(f"Ungültiges Farbformat: {color_string}. Erwartetes Format: R,G,B")

    def format_value(self):
        """Gibt den Wert als String für die Config-Datei aus."""
        if isinstance(self.value, bool):
            return "True" if self.value else "False"
        if isinstance(self.value, tuple):
            return ",".join(map(str, self.value))
        return str(self.value)