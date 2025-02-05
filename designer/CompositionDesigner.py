import os
import re
from datetime import timedelta

from PIL import Image

from designer.collage.CalendarGenerator import CalendarGenerator
from designer.collage.DescriptionGenerator import DescriptionGenerator
from designer.collage.MapGenerator import MapGenerator
from designer.collage.PhotoLayoutManager import PhotoLayoutManager
from designer.common.Config import Config


class CompositionDesigner:
    def __init__(self, config=None):
        self.config = config or Config()
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
        self.layoutManager = None
        if self.compositionTitle:
            self.startDate = self.config.startDate - timedelta(days=7)
        else:
            self.startDate = self.config.startDate

    def generate_collage(self, image_files, date, output_path, photo_description=""):
        """
        Creates a composition with pictures, a calendar and a map of Europe with photo locations.
        """
        collage = Image.new("RGB", (self.width, self.height), self.config.backgroundColor)
        available_height = self.height
        available_cal_width = self.width

        if self.compositionTitle:
            titleImage = self.calendarObj.generateTitle(
                self.compositionTitle, available_cal_width, self.calendar_height
            )
            collage.paste(titleImage, (self.config.marginSides, self.height - self.calendar_height))
            available_height -= self.calendar_height

        elif self.config.useCalendar and not self.compositionTitle:
            if self.config.usePhotoLocationMaps:
                available_cal_width -= self.config.mapWidth - self.config.marginSides
            calendarImage = self.calendarObj.generateCalendar(date, available_cal_width, self.calendar_height)
            collage.paste(calendarImage, (self.config.marginSides, self.height - self.calendar_height))
            available_height -= self.calendar_height

        if self.config.usePhotoDescription:
            descriptionImage = self.descGenerator.generateDescription(photo_description)
            collage.paste(descriptionImage, (0, self.height - self.calendar_height - self.descGenerator.height))
            available_height -= self.descGenerator.height

        available_width = self.width

        if len(image_files) == 0:
            print("No pictures found.")
            return

        # Arrange image collage
        self.layoutManager = PhotoLayoutManager(collage, available_width, available_height, self.spacing)
        self.layoutManager.arrangeImages(image_files)

        if self.config.usePhotoLocationMaps and not self.compositionTitle:
            imgMap = self.mapGenerator.generateImageLocationMap(image_files)
            collage.paste(imgMap, (self.width - self.config.mapWidth, self.height - self.config.mapHeight))

        # create title only once
        self.compositionTitle = None
        collage.save(output_path, quality=self.config.jpgQuality)
        print(f"Composition saved: {output_path}")

    def _process_images(self, image_files, output_prefix, description, start_date, max_images_per_collage=36):
        """
        Internal method for processing images in groups and creating collages.
        """
        for index, i in enumerate(range(0, len(image_files), max_images_per_collage)):
            collage_files = image_files[i : i + max_images_per_collage]
            output_file_name = f"{output_prefix}_part_{index + 1}.jpg"
            output_path = os.path.join(self.outputDir, output_file_name)

            # Berechne das Datum basierend auf dem Index (falls erforderlich)
            date = start_date + timedelta(weeks=index)

            # Wähle die passende Beschreibung aus der Liste oder verwende den Standard
            if isinstance(description, list) and index < len(description):
                collage_description = description[index]
            else:
                collage_description = description if isinstance(description, str) else ""

            self.generate_collage(collage_files, date, output_path, collage_description)

    @staticmethod
    def _get_description(folder_path, fallback_to_foldername=False):
        # Search for a text file in the folder
        photo_description = ""
        text_files = [
            os.path.join(folder_path, file) for file in sorted(os.listdir(folder_path)) if file.lower().endswith(".txt")
        ]
        if text_files:
            text_file = text_files[0]
            with open(text_file, "r", encoding="utf-8") as f:
                # Removes everything to the left of the colon including the colon
                photo_description = [re.sub(r"^[^:]*:\s*", "", line.strip()) for line in f.readlines() if line.strip()]

            if not photo_description and fallback_to_foldername:
                photo_description = os.path.splitext(os.path.basename(text_file))[0]

        return photo_description

    def generateProjectFromSubFolders(self):
        """
        Generates collages for all weeks from the specified folder.
        """
        descriptions = self._get_description(self.photoDirectory) or []  # Ensure that descriptions is a list
        weekIndex: int = 0
        for element in sorted(os.listdir(self.photoDirectory)):
            folder_path = os.path.join(self.photoDirectory, element)
            if not os.path.isdir(folder_path):
                continue

            # Collect all image files in the current folder
            image_files = [
                os.path.join(folder_path, file)
                for file in sorted(os.listdir(folder_path))
                if file.lower().endswith((".png", ".jpg", ".jpeg"))
            ]

            if not image_files:
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
            self._process_images(image_files, output_prefix, description, self.startDate + timedelta(weeks=weekIndex))
            weekIndex += 1

        if self.config.generatePdf:
            self.generate_pdf(self.outputDir)

    def generateProjectFromImageFolder(self):
        """
        Generates collages from a folder with flat images.
        """
        image_folder = self.photoDirectory
        if not os.path.isdir(image_folder):
            print(f"Folder {image_folder} does not exist.")
            return

        # Collect all image files in the folder
        image_files = [
            os.path.join(image_folder, file)
            for file in sorted(os.listdir(image_folder))
            if file.lower().endswith((".png", ".jpg", ".jpeg"))
        ]

        if not image_files:
            print(f"No images found in the {image_folder} folder.")
            return

        # Description and prefix for the collages
        folderName = os.path.basename(image_folder)
        output_prefix = f"collage_{folderName}"

        descriptions = self._get_description(image_folder)

        # Generate collages from flat images
        self._process_images(
            image_files, output_prefix, description=descriptions, start_date=self.startDate, max_images_per_collage=4
        )

        if self.config.generatePdf:
            self.generate_pdf(self.outputDir)

    @staticmethod
    def generate_pdf(collages_dir, output_pdf="output.pdf"):
        """
        Creates a PDF file from all images in a directory.

        :param collages_dir: Path to the directory with the images
        :param output_pdf: Name of the output file (default: output.pdf)
        """
        # Supported image formats
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}

        # Collect and sort all image files in the directory
        image_files = sorted(
            [f for f in os.listdir(collages_dir) if os.path.splitext(f)[1].lower() in image_extensions]
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
        first_image.save(output_path, save_all=True, append_images=remaining_images)

        print(f"PDF successfully created: {output_path}")


if __name__ == "__main__":
    # generate collage from separate folders
    colGen = CompositionDesigner()
    colGen.generateProjectFromSubFolders()
