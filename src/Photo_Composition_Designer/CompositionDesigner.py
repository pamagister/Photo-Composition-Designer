import os
import re
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from Photo_Composition_Designer.common.Locations import Locations
from Photo_Composition_Designer.common.Photo import get_photos_from_dir
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.CalendarGenerator import CalendarGenerator
from Photo_Composition_Designer.core.DescriptionGenerator import DescriptionGenerator
from Photo_Composition_Designer.core.MapGenerator import MapGenerator
from Photo_Composition_Designer.core.PhotoLayoutManager import PhotoLayoutManager


class CompositionDesigner:
    def __init__(self, config=None):
        self.config = config or ConfigParameterManager()
        self.compositionTitle = self.config.compositionTitle
        self.photoDirectory = self.config.photoDirectory
        self.outputDir = self.photoDirectory.parent / "collages"
        os.makedirs(self.outputDir, exist_ok=True)
        self.calendar_height = self.config.calendarHeight
        self.width = self.config.width
        self.height = self.config.height
        self.spacing = self.config.spacing
        self.calendarObj = CalendarGenerator(self.config)
        self.descGenerator = DescriptionGenerator(self.config)
        self.mapGenerator = MapGenerator(self.config)
        collage_height = self.get_available_collage_height()
        self.layoutManager = PhotoLayoutManager(
            self.width, collage_height, self.spacing, self.config.backgroundColor
        )
        if self.compositionTitle:
            self.startDate = self.config.startDate - timedelta(days=7)
        else:
            self.startDate = self.config.startDate

    def get_available_collage_height(self):
        available_height = self.height
        if self.config.useCalendar or self.compositionTitle:
            available_height -= (
                self.calendar_height + self.config.marginBottom + self.config.marginTop
            )
        if self.config.usePhotoDescription:
            available_height -= self.descGenerator.height
        return available_height

    def generate_composition(self, photos, date, output_path, photo_description=""):
        """
        Creates a composition with pictures, a calendar and a map of Europe with photo locations.
        """
        composition = Image.new("RGB", (self.width, self.height), self.config.backgroundColor)
        available_cal_width = self.width

        # add elements to the composition
        if self.compositionTitle:
            titleImage = self.calendarObj.generateTitle(
                self.compositionTitle, available_cal_width, self.calendar_height
            )
            composition.paste(
                titleImage, (self.config.marginSides, self.height - self.calendar_height)
            )

        elif self.config.useCalendar and not self.compositionTitle:
            if self.config.usePhotoLocationMaps:
                available_cal_width -= self.config.mapWidth + self.config.marginSides * 1
            calendarImage = self.calendarObj.generateCalendar(
                date, available_cal_width, self.calendar_height
            )
            composition.paste(
                calendarImage,
                (
                    self.config.marginSides,
                    self.height - self.calendar_height - self.config.marginBottom,
                ),
            )

        if self.config.usePhotoDescription:
            descriptionImage = self.descGenerator.generateDescription(photo_description)
            composition.paste(
                descriptionImage,
                (
                    0,
                    self.height
                    - self.calendar_height
                    - self.descGenerator.height
                    - self.config.marginBottom,
                ),
            )

        if len(photos) == 0:
            print("No pictures found.")
            return

        # Arrange image composition
        collage = self.layoutManager.arrangeImages(photos)
        composition.paste(collage, (0, self.config.marginTop))

        # add location map
        if self.config.usePhotoLocationMaps and not self.compositionTitle:
            coordinates = [
                location for photo in photos if (location := photo.get_location()) is not None
            ]
            imgMap = self.mapGenerator.generateImageLocationMap(coordinates)
            composition.paste(
                imgMap,
                (
                    self.width - self.config.mapWidth - self.config.marginSides,
                    self.height - self.config.mapHeight - self.config.marginBottom,
                ),
            )

        # draw dates of images into lower corner of the composition
        # TODO: Bessere Position finden, ggf. Größe mit der Karte verrechnen
        image_dates = [date for photo in photos if (date := photo.get_date()) is not None]

        unique_dates = set()  # Speichert bereits hinzugefügte Datumswerte
        date_str = ""

        for idx, date in enumerate(image_dates):
            formatted_date = date.strftime("%d. %b ")

            if formatted_date not in unique_dates:  # Nur hinzufügen, wenn noch nicht vorhanden
                unique_dates.add(formatted_date)
                date_str += formatted_date

            if len(unique_dates) >= 3:  # Maximal 3 verschiedene Daten
                break

        draw = ImageDraw.Draw(composition)
        font = CalendarGenerator.get_font(
            "DejaVuSansCondensed.ttf", int(self.config.fontSizeSmall * 0.8)
        )
        draw.text(
            (self.width - self.config.marginSides, self.height - self.config.marginBottom),
            date_str,
            font=font,
            fill=self.config.textColor2,
            anchor="rd",
        )

        # create title only once
        self.compositionTitle = None
        composition.save(
            output_path, quality=self.config.jpgQuality, dpi=(self.config.dpi, self.config.dpi)
        )
        print(f"Composition saved: {output_path}")

    def _process_images(
        self, photos, output_prefix, description, start_date, max_images_per_collage=36
    ):
        """
        Internal method for processing images in groups and creating collages.
        """
        for index, i in enumerate(range(0, len(photos), max_images_per_collage)):
            photos_for_collage = photos[i : i + max_images_per_collage]
            output_file_name = f"{output_prefix}_part_{index + 1}.jpg"
            output_path = os.path.join(self.outputDir, output_file_name)

            # Berechne das Datum basierend auf dem Index (falls erforderlich)
            date = start_date + timedelta(weeks=index)

            # Wähle die passende Beschreibung aus der Liste oder verwende den Standard
            if isinstance(description, list) and index < len(description):
                collage_description = description[index]
            else:
                collage_description = description if isinstance(description, str) else ""

            self.generate_composition(photos_for_collage, date, output_path, collage_description)

    @staticmethod
    def _get_description(folder_path, fallback_to_foldername=False):
        # Search for a text file in the folder
        photo_description = ""
        text_files = [
            os.path.join(folder_path, file)
            for file in sorted(os.listdir(folder_path))
            if file.lower().endswith(".txt")
        ]
        if text_files:
            text_file = text_files[0]
            with open(text_file, "r", encoding="utf-8") as f:
                # Removes everything to the left of the colon including the colon
                photo_description = [
                    re.sub(r"^[^:]*:\s*", "", line.strip())
                    for line in f.readlines()
                    if line.strip()
                ]

            if not photo_description and fallback_to_foldername:
                photo_description = os.path.splitext(os.path.basename(text_file))[0]

        return photo_description

    def generateProjectFromSubFolders(self):
        """
        Generates collages for all weeks from the specified folder.
        """
        descriptions = (
            self._get_description(self.photoDirectory) or []
        )  # Ensure that descriptions is a list
        weekIndex: int = 0
        for element in sorted(os.listdir(self.photoDirectory)):
            folder_path = os.path.join(self.photoDirectory, element)
            if not os.path.isdir(folder_path):
                continue

            # Collect all image files in the current folder
            locations = Locations(self.config.locationsConfig).locations_dict
            photos = get_photos_from_dir(Path(folder_path), locations)

            if not photos:
                print(f"No images found in {folder_path}, skip...")
                continue

            # Use the description from descriptions by default, if available
            description = descriptions[weekIndex] if weekIndex < len(descriptions) else ""

            # If `photo_description` exists, it overwrites the existing `description`.
            photo_description = self._get_description(folder_path, fallback_to_foldername=True)
            if photo_description:
                description = photo_description

            # Generate collages for this page
            output_prefix = f"collage_{element}"
            self._process_images(
                photos, output_prefix, description, self.startDate + timedelta(weeks=weekIndex)
            )
            weekIndex += 1

        if self.config.generatePdf:
            self.generate_pdf(self.outputDir)

    def generate_pdf(self, collages_dir, output_pdf="output.pdf"):
        """
        Creates a PDF file from all images in a directory.

        :param collages_dir: Path to the directory with the images
        :param output_pdf: Name of the output file (default: output.pdf)
        """
        # Supported image formats
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}

        # Collect and sort all image files in the directory
        image_files = sorted(
            [
                f
                for f in os.listdir(collages_dir)
                if os.path.splitext(f)[1].lower() in image_extensions
            ]
        )

        if not image_files:
            print("No images found in the directory.")
            return

        # Open and convert images
        image_list = []
        for image_file in image_files:
            img_path = os.path.join(collages_dir, image_file)
            img = Image.open(img_path).convert("RGB")  # Convert to RGB (for PDF compatible)
            image_list.append(img)

        # First image as base, attach remaining images as additional pages
        first_image, *remaining_images = image_list
        output_path = os.path.join(collages_dir, output_pdf)
        first_image.save(
            output_path,
            save_all=True,
            append_images=remaining_images,
            quality=self.config.jpgQuality,
            dpi=(self.config.dpi, self.config.dpi),
        )

        print(f"PDF successfully created: {output_path}")


if __name__ == "__main__":
    # generate collage from separate folders
    config = ConfigParameterManager("config/config.ini")
    colGen = CompositionDesigner(config)
    colGen.generateProjectFromSubFolders()
