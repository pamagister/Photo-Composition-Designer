import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS

from designer.common.Config import Config


class ImageSorter:
    DATE_PATTERN = re.compile(r"(?:(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2}))")

    def __init__(self, config=None):
        self.config = config or Config()
        self.photo_dir = self.config.photoDirectory
        self.output_dir = self.photo_dir.parent / "folders"
        self.start_date = self.config.startDate
        self.move_files = False
        self.unmatched_files = []
        self.sorted_images = {}
        self._prepare_weeks()

    def _prepare_weeks(self):
        """Erstellt eine Mapping-Struktur für Wochen (Mo-So, unabhängig vom Jahr)."""
        self.week_mapping = {}

        for week in range(52):
            week_start = self.start_date + timedelta(weeks=week)
            week_end = week_start + timedelta(days=6)
            self.week_mapping[(week_start.month, week_start.day)] = week_start.strftime(
                "%b_%Y-%m-%d"
            )

    def extract_date_from_exif(self, file_path):
        """Liest EXIF-Datum aus, falls vorhanden."""
        try:
            with Image.open(file_path) as img:
                exif_data = img._getexif()
                if exif_data:
                    for tag, value in exif_data.items():
                        tag_name = TAGS.get(tag, tag)
                        if tag_name == "DateTimeOriginal":
                            return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
        except Exception:
            pass
        return None

    def extract_date_from_filename(self, filename):
        """Versucht, Datum aus Dateinamen zu extrahieren."""
        match = self.DATE_PATTERN.search(filename)
        if match:
            year, month, day, hour, minute, second = map(int, match.groups())
            return datetime(year, month, day, hour, minute, second)
        return None

    def process_images(self):
        """Iteriert über Bilder, analysiert Datum und sortiert sie in die sortierte Liste ein"""
        for file in self.photo_dir.iterdir():
            if file.suffix.lower() not in [".jpg", ".jpeg", ".png"]:
                continue

            date = self.extract_date_from_exif(file) or self.extract_date_from_filename(
                file.name
            )
            if not date:
                self.unmatched_files.append(file)
            else:
                self.sorted_images[file] = date
        # self.sorted_images = sorted(self.sorted_images, key=self.sorted_images.get)

    def run(self):
        self.process_images()
        print(f"Unmatched files: {[f'{file.name}' for file in self.unmatched_files]}")
        print(f"Matched files: {[f'{value.name}' for value in self.sorted_images]}")


# Nutzung

sorter = ImageSorter()
sorter.run()
