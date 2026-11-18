import os
from collections import defaultdict

from photo_composition_designer.core.helpers import get_base_path

#: Bundled location files that are always loaded. English and German city and
#: country names are merged so filenames in either language resolve.
DEFAULT_LOCATION_FILES = ("locations_en.ini", "locations_de.ini")


class Locations:
    """
    This class is used to provide position information if it is not saved in the image.
    This class searches a locations.ini, which has the following structure below.

    It provides a dict that contains locations as tuple:

    [EUROPE]
    London = 51.5074, -0.1278
    Bavaria = 48.7904, 11.4979

    [AMERICA]
    United States = 37.0902, -95.7129

    By default the bundled English and German files are merged. An explicitly
    supplied file is loaded on its own so callers can parse a custom file in
    isolation; :meth:`with_overrides` adds such a file on top of the defaults.
    """

    def __init__(self, locations_file=None):
        self.locations_dict: dict[str, tuple[float, float]] = defaultdict(tuple)
        if locations_file:
            self._load_file(locations_file)
            return

        for name in DEFAULT_LOCATION_FILES:
            self._load_file(get_base_path() / name)

    def _load_file(self, locations_file: str | os.PathLike[str]) -> None:
        """Load one ini file into the location dictionary."""
        if not os.path.exists(locations_file):
            return

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

    def _add_to_dict(self, city: str, coordinates, _):
        """
        Adds an entry to the dictionary under the given category.
        """
        self.locations_dict[city.lower()] = coordinates

    def merge(self, other: "Locations") -> None:
        """Overlay another location set; entries from ``other`` win."""
        self.locations_dict.update(other.locations_dict)

    @classmethod
    def with_overrides(cls, locations_file=None) -> "Locations":
        """Return the bundled locations with an optional custom file on top."""
        locations = cls()
        if locations_file:
            locations.merge(cls(locations_file))
        return locations

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
