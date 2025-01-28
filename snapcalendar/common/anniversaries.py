import os
from configparser import ConfigParser
from pathlib import Path


class Anniversaries:
    def __init__(self, anniversaries_file=None):
        if not anniversaries_file:
            base_path = Path(__file__).parent.parent
            anniversaries_file = base_path / "anniversaries.ini"

        self.anniversary_dict = {}

        if not os.path.exists(anniversaries_file):
            return

        # ConfigParser so konfigurieren, dass Schlüssel (Namen) in Original-Schreibweise bleiben
        parser = ConfigParser()
        parser.optionxform = str  # Behalte die ursprüngliche Schreibweise der Namen
        parser.read(anniversaries_file, encoding="utf-8")

        # Kategorien mit ihren spezifischen Label-Formaten
        categories = {
            "Birthdays": lambda name, year: f"{name} {str(year)[-2:]}" if year else name,
            "Dates of death": lambda name, year: f"{name} ✝ {str(year)[-2:]}" if year else f"{name} ✝",
            "Weddings": lambda name, year: f"{name} ⚭ {str(year)[-2:]}" if year else f"{name} ⚭",
        }

        # Daten für jede Kategorie verarbeiten
        for category, label_formatter in categories.items():
            self._process_category(parser, category, label_formatter)

    def _process_category(self, parser, category, label_formatter):
        """
        Liest Einträge aus einer Kategorie in der Konfigurationsdatei und fügt sie zum Dictionary hinzu.
        :param parser: ConfigParser-Instanz
        :param category: Name der Kategorie (z. B. "Birthdays")
        :param label_formatter: Funktion zur Formatierung der Labels
        """
        if category in parser:
            for name, date in parser[category].items():
                day, month, *year = date.strip().split(".")
                year = int(year[0]) if year[0] else None
                label = label_formatter(name, year).split(" ")[0]
                self._add_to_dict(int(day), int(month), label)

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


if __name__ == "__main__":
    annis = Anniversaries()
    print(annis.items())
