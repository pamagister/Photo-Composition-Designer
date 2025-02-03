import re
from datetime import datetime

import exifread


class ImageDateAnalyzer:
    DATE_PATTERN_FULL = re.compile(r"(?:(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2}))")
    DATE_PATTERN_NO_TIME = re.compile(r"(?:(\d{4})(\d{2})(\d{2}))")

    def __init__(self, photo_files):
        self.photo_files: list(str) = photo_files

        self.undated_images: list[str] = []
        self.dated_images: dict[str:datetime] = {}

    @staticmethod
    def extract_date_from_exif(img_path):
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

    def extract_date_from_filename(self, img_path):
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

    def process_images(self):
        """Iterates over images, analyzes date and sorts them into the sorted list"""
        for file in self.photo_files:
            if file.suffix.lower() not in [".jpg", ".jpeg", ".png"]:
                continue

            date = self.extract_date_from_exif(file) or self.extract_date_from_filename(file.name)
            if not date:
                self.undated_images.append(file)
            else:
                self.dated_images[file] = date
        # self.sorted_images = sorted(self.sorted_images, key=self.sorted_images.get)

    def run(self):
        self.process_images()
        print(f"Unmatched files: {[f'{file.name}' for file in self.undated_images]}")
        print(f"Matched files: {[f'{value.name}' for value in self.dated_images]}")


# Nutzung
if __name__ == "__main__":
    sorter = ImageDateAnalyzer()
    sorter.run()
