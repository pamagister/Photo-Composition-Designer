import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import exifread


class ImageDateAnalyzer:
    DATE_PATTERN_FULL = re.compile(r"(?:(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2}))")
    DATE_PATTERN_NO_TIME = re.compile(r"(?:(\d{4})(\d{2})(\d{2}))")

    def __init__(self, image_files: list[str]):
        self.image_list: list[str] = image_files

        self.image_date_dict: dict[str:datetime] = {}
        self.images_undated: list[str] = []
        self._process_images()

    @staticmethod
    def extract_date_from_exif(img_path) -> Optional[datetime]:
        """Reads EXIF date, if available."""
        try:
            with open(img_path, "rb") as img_file:
                tags = exifread.process_file(img_file, details=False)
                if "EXIF DateTimeOriginal" in tags:
                    date = str(tags["EXIF DateTimeOriginal"])
                    return datetime.strptime(date, "%Y:%m:%d %H:%M:%S")
        except Exception as e:
            print(f"Error processing image {img_path}: {e}")
        return None

    def extract_date_from_filename(self, img_path: str) -> Optional[datetime]:
        """Attempts to extract date from file name."""
        match = self.DATE_PATTERN_FULL.search(img_path)
        if match:
            year, month, day, hour, minute, second = map(int, match.groups())
            return datetime(year, month, day, hour, minute, second)
        match = self.DATE_PATTERN_NO_TIME.search(img_path)
        if match:
            year, month, day = map(int, match.groups())
            return datetime(year, month, day, 12, 0, 0)
        return None

    def _process_images(self):
        """Iterates over images, analyzes date and sorts them into the sorted list"""
        for file in self.image_list:
            if Path(file).suffix.lower() not in [".jpg", ".jpeg", ".png"]:
                continue

            date = self.extract_date_from_exif(file) or self.extract_date_from_filename(file)
            if not date:
                self.images_undated.append(file)
            else:
                self.image_date_dict[file] = date

        print(f"Matched files: {[f'{value}' for value in self.image_date_dict]}")
        print(f"Unmatched files: {[f'{file}' for file in self.images_undated]}")


# Nutzung
if __name__ == "__main__":
    file_list = [
        "20230517_143025.jpg",
        "IMG_20230517_Holiday.jpg",
        "random_name.jpg",
    ]
    sorter = ImageDateAnalyzer(file_list)
    sorter.run()
