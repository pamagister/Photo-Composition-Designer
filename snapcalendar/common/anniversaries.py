from configparser import ConfigParser
import os


class Anniversaries:
    def __init__(self, config_file="anniversaries.ini"):
        self.anniversary_dict = {}

        if not os.path.exists(config_file):
            return

        # ConfigParser so konfigurieren, dass Schlüssel (Namen) in Original-Schreibweise bleiben
        parser = ConfigParser()
        parser.optionxform = str  # Behalte die ursprüngliche Schreibweise der Namen
        parser.read(config_file, encoding="utf-8")

        # Geburtstage aus der Konfigurationsdatei lesen
        if "Birthdays" in parser:
            for name, date in parser["Birthdays"].items():
                day, month, *year = date.strip().split(".")
                year = int(year[0]) if year[0] else None
                birthday_label = f"{name} {str(year)[-2:]}" if year else name
                self._add_to_dict(int(day), int(month), birthday_label)

        # Todestage aus der Konfigurationsdatei lesen
        if "Dates of death" in parser:
            for name, date in parser["Dates of death"].items():
                day, month, *year = date.strip().split(".")
                year = int(year[0]) if year else None
                death_label = f"{name} ✝ {str(year)[-2:]}" if year else f"{name} ✝"
                self._add_to_dict(int(day), int(month), death_label)

        # Hochzeitstage aus der Konfigurationsdatei lesen
        if "Weddings" in parser:
            for name, date in parser["Weddings"].items():
                day, month, *year = date.strip().split(".")
                year = int(year[0]) if year else None
                wedding_label = f"{name} ⚭ {str(year)[-2:]}" if year else f"{name} ⚭"
                self._add_to_dict(int(day), int(month), wedding_label)

    def _add_to_dict(self, day, month, label):
        """Hinzufügen eines Eintrags zum Datum; bei Konflikten zusammenfügen."""
        key = (day, month)
        if key in self.anniversary_dict:
            self.anniversary_dict[key] += f", {label}"
        else:
            self.anniversary_dict[key] = label

    def __getitem__(self, key):
        return self.anniversary_dict.get(key)

    def __setitem__(self, key, value):
        self.anniversary_dict[key] = value

    def __contains__(self, key):
        return key in self.anniversary_dict

    def items(self):
        return self.anniversary_dict.items()

    def __repr__(self):
        return f"Anniversaries({self.anniversary_dict})"
