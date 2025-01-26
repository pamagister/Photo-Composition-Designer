from configparser import ConfigParser
import os


class Birthdays:
    def __init__(self, config_file="birthdays.ini"):
        self.birthday_dict = {}

        if not os.path.exists(config_file):
            return

        # ConfigParser so konfigurieren, dass Schlüssel (Namen) in Original-Schreibweise bleiben
        parser = ConfigParser()
        parser.optionxform = str  # Behalte die ursprüngliche Schreibweise der Namen
        parser.read(config_file, encoding="utf-8")

        # Geburtstage aus der Konfigurationsdatei lesen
        if "Birthdays" in parser:
            for name, date in parser["Birthdays"].items():
                date = date.strip()
                if date.startswith("+"):  # Todestage
                    day, month, *year = date[1:].split(".")
                    year = int(year[0]) if year else None
                    self.birthday_dict[(int(day), int(month))] = f"{name} \u271D"
                else:  # Geburtstage
                    day, month, *year = date.split(".")
                    year = int(year[0]) if year[0] else None
                    birthday_label = f"{name} {str(year)[-2:]}" if year else name
                    self.birthday_dict[(int(day), int(month))] = birthday_label

    def __getitem__(self, key):
        return self.birthday_dict.get(key)

    def __setitem__(self, key, value):
        self.birthday_dict[key] = value

    def __contains__(self, key):
        return key in self.birthday_dict

    def items(self):
        return self.birthday_dict.items()

    def __repr__(self):
        return f"Birthdays({self.birthday_dict})"
