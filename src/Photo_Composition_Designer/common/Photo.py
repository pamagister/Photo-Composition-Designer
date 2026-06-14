import os
import re
from datetime import datetime
from pathlib import Path

import exifread
from PIL import Image


class Photo:
    """
    Represents a photo file, providing methods to extract metadata like
    location and date from EXIF data or filename.
    """

    DATE_PATTERN_FULL: re.Pattern = re.compile(
        r"(?:(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2}))"
    )
    DATE_PATTERN_NO_TIME: re.Pattern = re.compile(r"(?:(\d{4})[-_]?(\d{2})[-_]?(\d{2}))")

    def __init__(self, file_path: Path, locations=None):
        self.file_path: Path = Path(file_path)
        self._locations: dict[str, tuple[float, float]] = locations
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

    def get_location(self) -> tuple[float, float] | None:
        """
        Returns the GPS coordinates if available
        using EXIF or filename.
        """
        return self.get_location_from_exif() or self.get_location_from_name()

    def get_location_from_exif(self) -> tuple[float, float] | None:
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

    def get_location_from_name(self) -> tuple[float, float] | None:
        """
        Extracts location from the filename based on predefined locations.
        """
        location = self._locations
        file_name = self.file_path.name.lower()

        for place in location:
            if re.search(rf"\b{re.escape(place.lower())}\b", file_name):
                return location[place]

        return None

    def get_date(self) -> datetime | None:
        """Returns the date from EXIF data or filename if available."""
        date = self._extract_date_from_exif()
        if date:
            return date
        return self._extract_date_from_filename()

    def get_image(self) -> Image.Image | None:
        """Returns an Image object if the file can be opened."""
        try:
            return Image.open(self.file_path)
        except (OSError, SyntaxError) as e:
            print(f"Error opening image: {e}")
            return None

    @staticmethod
    def _convert_to_decimal(dms) -> float:
        """Converts degrees, minutes, and seconds to decimal degrees."""
        return float(dms[0]) + float(dms[1]) / 60 + float(dms[2]) / 3600

    def _extract_date_from_exif(self) -> datetime | None:
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

    def _extract_date_from_filename(self) -> datetime:
        """Attempts to extract date from file name."""

        patterns = (
            (self.DATE_PATTERN_FULL, ()),
            (self.DATE_PATTERN_NO_TIME, (12, 0, 0)),
        )

        for pattern, defaults in patterns:
            match = pattern.search(self.file_path.name)
            if not match:
                continue

            try:
                return datetime(*map(int, match.groups()), *defaults)
            except ValueError:
                continue

        return datetime.max


def get_photos_from_dir(
    image_folder: Path, locations: dict[str, tuple[float, float]] = None
) -> list[Photo]:
    """
    Reads all image files from a folder and returns a list of Photo objects.
    """
    folder_path = Path(image_folder)

    if not folder_path.is_dir():
        raise ValueError(f"Folder '{image_folder}' does not exist.")

    # Collect all image files
    image_files = [
        os.path.join(image_folder, file)
        for file in sorted(os.listdir(image_folder))
        if file.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    return [Photo(Path(file), locations) for file in image_files]


def get_photo_dates(photos: list[Photo]) -> str:
    """
    Get a string of at most 3 unique dates from a list of photos
    """
    image_dates = [d for photo in photos if (d := photo.get_date()) is not None]
    unique_dates = set()
    date_str = ""
    for d in image_dates:
        formatted = d.strftime("%d. %b ")
        if formatted not in unique_dates:
            unique_dates.add(formatted)
            date_str += formatted
        if len(unique_dates) >= 3:
            break
    return date_str
