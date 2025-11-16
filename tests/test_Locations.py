from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from common.Locations import Locations


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
