from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from Photo_Composition_Designer.common.Anniversaries import Anniversaries


class TestAnniversaries:
    @pytest.fixture
    def sample_anniversaries_file(self):
        """
        Creates a temporary anniversaries.ini file with sample data.
        """
        data = """
        [Birthdays]
        Paul = 6.1.
        Anna = 07.1.1984
        Peter = 08.01.
        Liz = 09.01.1993
        Anna = 10.01.

        [Dates of death]
        Gisela = 11.01.2020
        Helmut = 08.01.2023

        [Weddings]
        Mary & Josh = 12.01.2021
        """
        with NamedTemporaryFile("w", delete=False, suffix=".ini") as temp_file:
            temp_file.write(data)
            temp_file_path = temp_file.name
        yield temp_file_path
        Path(temp_file_path).unlink()  # Remove the file after the test

    def test_anniversaries_parsing(self, sample_anniversaries_file):
        """
        Tests the Anniversaries class with sample data.
        """
        # Initialize Anniversaries with the temporary file
        anniversaries = Anniversaries(sample_anniversaries_file)

        # Expected output
        expected = {
            (6, 1): "Paul",
            (7, 1): "Anna 84",
            (8, 1): "Peter, Helmut ✝ 23",
            (9, 1): "Liz 93",
            (10, 1): "Anna",
            (11, 1): "Gisela ✝ 20",
            (12, 1): "Mary & Josh ⚭ 21",
        }

        # Assert that the parsed output matches the expected result
        assert dict(anniversaries.items()) == expected
