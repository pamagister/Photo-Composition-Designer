from datetime import datetime
from pathlib import Path

import pytest

from designer.tools.ImageDateAnalyzer import ImageDateAnalyzer


class TestImageDateAnalyzer:
    EXAMPLE_IMAGE_1 = Path(__file__).parent.parent / "images" / "layout_orientation" / "landscape1.jpg"
    EXAMPLE_IMAGE_2 = Path(__file__).parent.parent / "images" / "layout_orientation" / "landscape2.jpg"
    EXAMPLE_IMAGE_5 = Path(__file__).parent.parent / "images" / "layout_orientation" / "landscape5.jpg"
    TEST_DATE = datetime(2023, 5, 17, 14, 30, 25)
    TEST_DATE_NO_TIME = datetime(2023, 5, 17, 12, 0, 0)

    def test_extract_date_from_exif(self):
        sorter = ImageDateAnalyzer([])
        date = sorter.extract_date_from_exif(self.EXAMPLE_IMAGE_2.as_posix())
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

    def test_process_images_exif(self):
        file1 = self.EXAMPLE_IMAGE_1.as_posix()
        file2 = self.EXAMPLE_IMAGE_2.as_posix()
        file5 = self.EXAMPLE_IMAGE_5.as_posix()

        file_list = [file1, file2, file5]

        sorter = ImageDateAnalyzer(file_list)

        expectedDate2 = datetime(2023, 7, 31, 18, 54, 56)

        assert len(sorter.image_date_dict) == 2
        assert len(sorter.images_undated) == 1
        assert sorter.image_date_dict[file2] == expectedDate2

    def test_process_images_from_filename(self):
        file_list = [
            "20230517_143025.jpg",
            "IMG_20230517-143025.jpeg",
            "IMG_20230517.jpeg",
            "IMG_20230517_143025_sometext.jpeg",
            "IMG_20230517_Holiday.jpg",
            "random_name.jpg",
        ]

        sorter = ImageDateAnalyzer(file_list)

        assert len(sorter.image_date_dict) == 5
        assert len(sorter.images_undated) == 1
        assert sorter.image_date_dict[file_list[0]] == self.TEST_DATE
