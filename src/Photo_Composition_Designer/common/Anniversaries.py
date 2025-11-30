import os
from collections import defaultdict

from path_handler import get_base_path


class Anniversaries:
    def __init__(self, anniversaries_file=None):
        if not anniversaries_file:
            base_path = get_base_path()
            anniversaries_file = base_path / "anniversaries.ini"

        self.anniversary_dict = defaultdict(str)  # Dictionary für die Anniversaries

        if not os.path.exists(anniversaries_file):
            return

        # Preprocess the config file to remove comments and parse lines
        with open(anniversaries_file, "r", encoding="utf-8") as file:
            category = None
            for line in file:
                # Remove comments and strip whitespace
                line = line.split(";", 1)[0].strip()
                if not line:  # Skip empty lines
                    continue

                # Detect category headers
                if line.startswith("[") and line.endswith("]"):
                    category = line[1:-1]  # Extract category name
                    continue

                # Skip invalid lines without a current category
                if not category:
                    continue

                # Process valid data lines within the category
                self._process_line(line, category)

    def _process_line(self, line, category):
        """
        Processes a single line of data and adds it to the anniversary dictionary.
        """
        if "=" not in line:
            return  # Skip malformed lines
        name, date = map(str.strip, line.split("=", 1))

        day, month, *year = date.split(".")
        year = int(year[0]) if year and year[0] else None

        # Define label formatters for each category
        label_formatter = {
            "Birthdays": lambda _name, _year: f"{_name} {str(_year)[-2:]}" if _year else _name,
            "Dates of death": lambda _name, _year: f"{_name} ✝ {str(_year)[-2:]}"
            if _year
            else f"{_name} ✝",
            "Weddings": lambda _name, _year: f"{_name} ⚭ {str(_year)[-2:]}"
            if _year
            else f"{_name} ⚭",
        }.get(category, lambda _name, _year: _name)  # Default formatter if category is unknown

        label = label_formatter(name, year)
        self._add_to_dict(int(day), int(month), label)

    def _add_to_dict(self, day, month, label):
        """
        Adds an entry to the dictionary; merges labels in case of conflicts.
        """
        key = (day, month)
        if key in self.anniversary_dict:
            if label not in self.anniversary_dict[key]:
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
        return f"Anniversaries({dict(self.anniversary_dict)})"


if __name__ == "__main__":
    annis = Anniversaries()
    print(annis.items())
