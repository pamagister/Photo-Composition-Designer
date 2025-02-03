from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from designer.tools.ImageDateAnalyzer import ImageDateAnalyzer


class TestImageDateAnalyzer:

    EXAMPLE_IMAGE_1 = Path(__file__).parent.parent / "images" / "layout_orientation" / "landscape2.jpg"
    EXAMPLE_IMAGE_2 = Path(__file__).parent.parent / "images" / "layout_orientation" / "landscape5.jpg"
    TEST_DATE = datetime(2023, 5, 17, 14, 30, 25)
    TEST_DATE_NO_TIME = datetime(2023, 5, 17, 12, 0, 0)

    def test_extract_date_from_exif(self):
        sorter = ImageDateAnalyzer([self.EXAMPLE_IMAGE_1])
        date = sorter.extract_date_from_exif(self.EXAMPLE_IMAGE_1)
        assert date == datetime(2023, 7, 31, 18, 54, 56)

    @pytest.mark.parametrize(
        "filename, expected_date",
        [
            ("20230517_143025.jpg", TEST_DATE),
            ("IMG_20230517-143025.jpeg", TEST_DATE),
            ("IMG_20230517.jpeg", TEST_DATE_NO_TIME),
            ("IMG_20230517_143025_sometext.jpeg", TEST_DATE),
            ("IMG_20230517_Holiday.jpg", TEST_DATE_NO_TIME),
            ("random_name.jpg", None),
        ],
    )
    def test_extract_date_from_filename(self, filename, expected_date):
        sorter = ImageDateAnalyzer([])
        date = sorter.extract_date_from_filename(filename)
        assert date == expected_date

    def test_process_images(self):
        file1 = self.EXAMPLE_IMAGE_1
        file2 = self.EXAMPLE_IMAGE_2

        file3 = MagicMock()
        file3.suffix = ".jpg"
        file3.name = "20230517_143025.jpg"

        file4 = MagicMock()
        file4.suffix = ".jpg"
        file4.name = "random.jpg"

        file_list = [file1, file2, file3, file4]

        sorter = ImageDateAnalyzer(file_list)
        sorter.process_images()

        assert len(sorter.dated_images) == 3
        assert len(sorter.undated_images) == 1
        assert sorter.dated_images[file3] == datetime.fromisoformat("20230517_143025")

    @patch.object(ImageDateAnalyzer, "process_images")
    def test_run(self, mock_process):
        sorter = ImageDateAnalyzer([])
        sorter.run()
        mock_process.assert_called_once()
