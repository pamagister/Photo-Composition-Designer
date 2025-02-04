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
        Erzeugt eine Composition mit Bildern, einem Calendarium und einer Europakarte mit Foto-Locations.
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
        print(f"Composition gespeichert: {output_path}")

    def _process_images(self, image_files, output_prefix, description, start_date, max_images_per_collage=36):
        """
        Interne Methode, um Bilder in Gruppen zu verarbeiten und Collagen zu erstellen.
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
        # Suche nach einer Textdatei im Ordner
        photo_description = ""
        text_files = [
            os.path.join(folder_path, file) for file in sorted(os.listdir(folder_path)) if file.lower().endswith(".txt")
        ]
        if text_files:
            text_file = text_files[0]
            with open(text_file, "r", encoding="utf-8") as f:
                # Entfernt alles links vom Doppelpunkt inklusive Doppelpunkt
                photo_description = [re.sub(r"^[^:]*:\s*", "", line.strip()) for line in f.readlines() if line.strip()]

            if not photo_description and fallback_to_foldername:
                photo_description = os.path.splitext(os.path.basename(text_file))[0]

        return photo_description

    def generateProjectFromSubFolders(self):
        """
        Generiert Collagen für alle Wochen aus dem angegebenen Ordner.
        """
        descriptions = (
            self._get_description(self.photoDirectory) or []
        )  # Sicherstellen, dass descriptions eine Liste ist
        weekIndex: int = 0
        for week_index, element in enumerate(sorted(os.listdir(self.photoDirectory))):
            folder_path = os.path.join(self.photoDirectory, element)
            if not os.path.isdir(folder_path):
                continue

            # Sammle alle Bilddateien im aktuellen Ordner
            image_files = [
                os.path.join(folder_path, file)
                for file in sorted(os.listdir(folder_path))
                if file.lower().endswith((".png", ".jpg", ".jpeg"))
            ]

            if not image_files:
                print(f"Keine Bilder in {folder_path} gefunden, überspringe...")
                continue

            # Standardmäßig die Beschreibung aus descriptions nutzen, falls vorhanden
            description = descriptions[week_index] if week_index < len(descriptions) else ""

            # Falls `photo_description` existiert, überschreibt es die bestehende `description`
            photo_description = self._get_description(folder_path, fallback_to_foldername=True)
            if photo_description:
                description = photo_description

            # Generiere Collagen für die Woche
            output_prefix = f"collage_{element}"
            self._process_images(image_files, output_prefix, description, self.startDate + timedelta(weeks=weekIndex))
            weekIndex += 1

    def generateProjectFromImageFolder(self):
        """
        Generiert Collagen aus einem Ordner mit flachen Bildern.
        """
        image_folder = self.photoDirectory
        if not os.path.isdir(image_folder):
            print(f"Ordner {image_folder} existiert nicht.")
            return

        # Sammle alle Bilddateien im Ordner
        image_files = [
            os.path.join(image_folder, file)
            for file in sorted(os.listdir(image_folder))
            if file.lower().endswith((".png", ".jpg", ".jpeg"))
        ]

        if not image_files:
            print(f"Keine Bilder im Ordner {image_folder} gefunden.")
            return

        # Beschreibung und Präfix für die Collagen
        folderName = os.path.basename(image_folder)
        output_prefix = f"collage_{folderName}"

        descriptions = self._get_description(image_folder)

        # Generiere Collagen aus flachen Bildern
        self._process_images(
            image_files, output_prefix, description=descriptions, start_date=self.startDate, max_images_per_collage=4
        )


if __name__ == "__main__":
    # generate collage from separate folders
    colGen = CompositionDesigner()
    colGen.generateProjectFromSubFolders()
