import os
from datetime import timedelta

from PIL import Image

from snapcalendar.collage.calendarGenerator import CalendarGenerator
from snapcalendar.collage.descriptionGenerator import DescriptionGenerator
from snapcalendar.collage.mapGenerator import MapGenerator
from snapcalendar.collage.photoLayoutManager import PhotoLayoutManager
from snapcalendar.common.config import Config


class CollageGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.photoDirectory = self.config.photoDirectory
        self.outputDir = self.photoDirectory.parent / 'collages'
        os.makedirs(self.outputDir, exist_ok=True)
        self.calendar_height = self.config.calendarHeight
        self.width = self.config.width
        self.height = self.config.height
        self.spacing = self.config.spacing
        self.calendarObj = CalendarGenerator(self.config)
        self.descGenerator = DescriptionGenerator()
        self.mapGenerator = MapGenerator()
        self.layoutManager = None
        self.startDate = self.config.startDate

    def generate_collage(self, image_files, date, output_path, photo_description=''):
        """
        Erzeugt eine Collage mit Bildern, einem Calendarium und einer Europakarte mit Foto-Locations.
        """
        collage = Image.new("RGB", (self.width, self.height), self.config.backgroundColor)
        calendarImage = self.calendarObj.generateCalendarium(date)
        collage.paste(calendarImage, (0, self.height - self.calendar_height))

        if self.config.usePhotoDescription:
            descriptionImage = self.descGenerator.generateDescription(photo_description)
            collage.paste(descriptionImage, (0, self.height - self.calendar_height - self.descGenerator.height))

        available_height = self.height - self.calendar_height - self.descGenerator.height
        available_width = self.width

        if len(image_files) == 0:
            print(f"Keine Bilder gefunden.")
            return

        self.layoutManager = PhotoLayoutManager(collage, available_width, available_height)

        # Anordnungslogik basierend auf Bildanzahl
        self.layoutManager.arrange_images(image_files)

        # Wenn GPS-Koordinaten vorliegen, eine Karte generieren
        if self.config.usePhotoLocationMaps:
            # EXIF-Daten auslesen und GPS-Koordinaten extrahieren
            gps_coords = []
            for img_path in image_files:
                coords = self.mapGenerator.extract_gps_coordinates(img_path)
                if coords:
                    gps_coords.append(coords)
            map_image = self.mapGenerator.generate_map(gps_coords)
            map_image_resized = map_image.resize((self.calendar_height, self.calendar_height))
            collage.paste(map_image_resized, (self.width - self.calendar_height, self.height - self.calendar_height))

        collage.save(output_path, quality=self.config.jpgQuality)
        print(f"Collage gespeichert: {output_path}")

    def _process_images(self, image_files, output_prefix, description, start_date, max_images_per_collage=100):
        """
        Interne Methode, um Bilder in Gruppen zu verarbeiten und Collagen zu erstellen.
        """
        for index, i in enumerate(range(0, len(image_files), max_images_per_collage)):
            collage_files = image_files[i: i + max_images_per_collage]
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
                photo_description = [line.strip() for line in f.readlines() if line.strip()]

            if not photo_description and fallback_to_foldername:
                photo_description = os.path.splitext(os.path.basename(text_file))[0]
        return photo_description

    def generateProjectFromSubFolders(self):
        """
        Generiert Collagen für alle Wochen aus dem angegebenen Ordner.
        """
        for weekIndex, folder in enumerate(sorted(os.listdir(self.photoDirectory))):
            folder_path = os.path.join(self.photoDirectory, folder)
            if os.path.isdir(folder_path):
                # Sammle alle Bilddateien im aktuellen Ordner
                image_files = [
                    os.path.join(folder_path, file)
                    for file in sorted(os.listdir(folder_path))
                    if file.lower().endswith((".png", ".jpg", ".jpeg"))
                ]

                if not image_files:
                    print(f"Keine Bilder in {folder_path} gefunden, überspringe...")
                    continue

                photo_description = self._get_description(folder_path, fallback_to_foldername=True)

                # Generiere Collagen für die Woche
                output_prefix = f"collage_{folder}"
                self._process_images(
                    image_files, output_prefix, photo_description, self.startDate + timedelta(weeks=weekIndex)
                )

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
    colGen = CollageGenerator()
    colGen.generateProjectFromSubFolders()
