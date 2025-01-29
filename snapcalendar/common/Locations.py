import os
from collections import defaultdict
from pathlib import Path


class Locations:
    """
    This class is used to provide position information if it is not saved in the image.
    This class searches a locations.ini, which has the following structure below.

    It provides a dict that contains locations as tuple: (52.5200, 13.5156)

    [GERMANY]
    Dresden = 51.0504, 13.7373
    Leipzig = 51.3397, 12.3731
    Chemnitz= 50.8278, 12.9214
    Breslau = 51.1079, 17.0441
    Berlin = 52.5200, 13.5156

    [EUROPE]
    London = ....

    [NORTH AMERICA]

    [SOUTH AMERICA]

    [ASIA]

    [AFRICA]

    [AUSTRALIA]
    """

    def __init__(self, locations_file=None):
        if not locations_file:
            base_path = Path(__file__).parent.parent
            locations_file = base_path / "locations.ini"

        self.locations_dict = defaultdict(tuple)  # Dictionary for the locations

        if not os.path.exists(locations_file):
            return

        # Preprocess the config file to remove comments and parse lines
        with open(locations_file, "r", encoding="utf-8") as file:
            current_category = None
            for line in file:
                # Remove comments and strip whitespace
                line = line.split(";", 1)[0].strip()
                if not line:  # Skip empty lines
                    continue

                # Detect category headers
                if line.startswith("[") and line.endswith("]"):
                    current_category = line[1:-1]
                    continue

                # Process valid data lines within the category
                self._process_line(line, current_category)

    def _process_line(self, line, category):
        """
        Processes a single line of data and adds it to the locations dictionary.
        """
        if "=" not in line:
            return  # Skip malformed lines
        city, coordinates = map(str.strip, line.split("=", 1))
        try:
            lat, lon = map(float, coordinates.split(","))
            self._add_to_dict(city, (lat, lon), category)
        except Exception as e:
            print(f'Error processing line "{line}": {e}')

    def _add_to_dict(self, city, coordinates, _):
        """
        Adds an entry to the dictionary under the given category.
        """
        self.locations_dict[city] = coordinates

    def __getitem__(self, key):
        return self.locations_dict.get(key)

    def __setitem__(self, key, value):
        self.locations_dict[key] = value

    def __contains__(self, key):
        return key in self.locations_dict

    def items(self):
        return self.locations_dict.items()

    def __repr__(self):
        return f"Locations({dict(self.locations_dict)})"


if __name__ == "__main__":
    locations = Locations()
    print(locations.items())
