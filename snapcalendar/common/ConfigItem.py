
class ConfigItem:
    """Speichert Konfigurationswerte mit Beschreibung."""

    def __init__(self, category, key, value, value_type, description):
        self.category = category
        self.key = key
        self.value = value
        self.value_type = value_type
        self.description = description

    def get_value(self, config_parser):
        """Liest einen Wert aus dem ConfigParser und konvertiert ihn ins richtige Format."""
        if self.value_type == bool:
            return config_parser.getboolean(self.category, self.key, fallback=self.value)
        elif self.value_type == int:
            return config_parser.getint(self.category, self.key, fallback=self.value)
        elif self.value_type == float:
            return config_parser.getfloat(self.category, self.key, fallback=self.value)
        else:
            return config_parser.get(self.category, self.key, fallback=self.value)

    def format_value(self):
        """Gibt den Wert als String für die Config-Datei aus."""
        if isinstance(self.value, bool):
            return "True" if self.value else "False"
        if isinstance(self.value, tuple):
            return ",".join(map(str, self.value))
        return str(self.value)