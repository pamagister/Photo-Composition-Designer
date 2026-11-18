from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from photo_composition_designer.core.locations import Locations


class TestLocations:
    @pytest.fixture
    def sample_file(self):
        """
        Creates a temporary anniversaries.ini file with sample data.
        """
        data = """
        [GERMANY]
        Dresden = 51.0504, 13.7373
        Leipzig = 51.3397, 12.3731
        Chemnitz = 50.8278, 12.9214
        """
        with NamedTemporaryFile("w", delete=False, suffix=".ini") as temp_file:
            temp_file.write(data)
            temp_file_path = temp_file.name
        yield temp_file_path
        Path(temp_file_path).unlink()  # Remove the file after the test

    def test_locations_parsing(self, sample_file):
        """
        Tests the Anniversaries class with sample data.
        """
        # Initialize Anniversaries with the temporary file
        locations = Locations(sample_file)

        # Expected output
        expected = {
            "dresden": (51.0504, 13.7373),
            "leipzig": (51.3397, 12.3731),
            "chemnitz": (50.8278, 12.9214),
        }

        # Assert that the parsed output matches the expected result
        assert dict(locations.items()) == expected

    def test_default_loads_bundled_german_and_english_names(self):
        locations = Locations()

        assert locations["frankfurt"] == (50.1109, 8.6821)
        assert locations["wien"] == (48.2082, 16.3738)
        assert locations["munich"] == (48.1351, 11.5820)

    def test_with_overrides_adds_and_replaces_bundled_entries(self, tmp_path):
        custom = tmp_path / "locations.ini"
        custom.write_text(
            "[CUSTOM]\nFrankfurt = 1.0, 2.0\nWeimar = 50.9795, 11.3235\n",
            encoding="utf-8",
        )

        locations = Locations.with_overrides(custom)

        assert locations["frankfurt"] == (1.0, 2.0)
        assert locations["weimar"] == (50.9795, 11.3235)
        assert locations["paris"] == (48.8566, 2.3522)
