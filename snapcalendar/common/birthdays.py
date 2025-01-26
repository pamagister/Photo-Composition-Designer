from configparser import ConfigParser
import os


class Birthdays:
    def __init__(self, config_file="birthdays.ini"):
        self.birthday_dict = {}

        if not os.path.exists(config_file):
            return {}

        parser = ConfigParser()
        parser.read(config_file, encoding="utf-8")

        if "Birthdays" in parser:
            for name, date in parser["Birthdays"].items():
                date = date.strip()
                if date.startswith("+"):  # Todestage
                    day, month, *year = date[1:].split(".")
                    year = int(year[0]) if year else None
                    self.birthday_dict[(int(day), int(month))] = f"{name} ✝"
                else:  # Geburtstage
                    day, month, *year = date.split(".")
                    year = int(year[0]) if year[0] else None
                    birthday_label = f"{name} {str(year)[-2:]}" if year else name
                    self.birthday_dict[(int(day), int(month))] = birthday_label


    def __repr__(self):
        return f"Config({self.__dict__})"