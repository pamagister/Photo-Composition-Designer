import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import exifread
from PIL import Image


class Photo:
    DATE_PATTERN_FULL = re.compile(r"(?:(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2}))")
    DATE_PATTERN_NO_TIME = re.compile(r"(?:(\d{4})[-_]?(\d{2})[-_]?(\d{2}))")

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

    def get_location(self) -> Optional[Tuple[float, float]]:
        """Returns the GPS coordinates from EXIF data if available."""
        with open(self.file_path, "rb") as img_file:
            tags = exifread.process_file(img_file, details=False)
            if "GPS GPSLatitude" in tags and "GPS GPSLongitude" in tags:
                lat = self._convert_to_decimal(tags["GPS GPSLatitude"].values)
                lon = self._convert_to_decimal(tags["GPS GPSLongitude"].values)
                if tags.get("GPS GPSLatitudeRef") and tags["GPS GPSLatitudeRef"].values[0] == "S":
                    lat = -lat
                if tags.get("GPS GPSLongitudeRef") and tags["GPS GPSLongitudeRef"].values[0] == "W":
                    lon = -lon
                return lat, lon
        return None

    def get_date(self) -> Optional[datetime]:
        """Returns the date from EXIF data or filename if available."""
        date = self._extract_date_from_exif()
        if date:
            return date
        return self._extract_date_from_filename()

    def get_image(self) -> Optional[Image.Image]:
        """Returns an Image object if the file can be opened."""
        try:
            return Image.open(self.file_path)
        except Exception as e:
            print(f"Error opening image: {e}")
            return None

    @staticmethod
    def _convert_to_decimal(dms) -> float:
        """Converts degrees, minutes, and seconds to decimal degrees."""
        return float(dms[0]) + float(dms[1]) / 60 + float(dms[2]) / 3600

    def _extract_date_from_exif(self) -> Optional[datetime]:
        """Reads EXIF date, if available."""
        with open(self.file_path, "rb") as img_file:
            tags = exifread.process_file(img_file, details=False)
            if "EXIF DateTimeOriginal" in tags:
                try:
                    date_str = str(tags["EXIF DateTimeOriginal"])
                    return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass
        return None

    def _extract_date_from_filename(self) -> Optional[datetime]:
        """Attempts to extract date from file name."""
        match = self.DATE_PATTERN_FULL.search(self.file_path.name)
        if match:
            return datetime(*map(int, match.groups()))
        match = self.DATE_PATTERN_NO_TIME.search(self.file_path.name)
        if match:
            return datetime(*map(int, match.groups()), 12, 0, 0)
        return None
