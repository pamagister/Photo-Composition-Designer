import os
from datetime import timedelta
from pathlib import Path

from PIL import Image

from snapcalendar.common.config import Config
from snapcalendar.collage.calendarGenerator import CalendarGenerator
from snapcalendar.collage.descriptionGenerator import DescriptionGenerator
from snapcalendar.collage.mapGenerator import MapGenerator
from snapcalendar.collage.photoLayoutManager import PhotoLayoutManager


class CollageGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.photoDirectory = Path(self.config.photoDirectory).resolve()
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

        images = [Image.open(img) for img in image_files]
        self.layoutManager = PhotoLayoutManager(collage, available_width, available_height)

        # Anordnungslogik basierend auf Bildanzahl
        self.layoutManager.arrange_images(images)

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

        collage.save(output_path)
        print(f"Collage gespeichert: {output_path}")

    def generateWeekCollages(self):
        """
        Generiert Collagen für alle Wochen aus dem angegebenen Ordner
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

                # Suche nach einer Textdatei im Ordner
                photo_description = ""
                text_files = [
                    os.path.join(folder_path, file)
                    for file in sorted(os.listdir(folder_path))
                    if file.lower().endswith(".txt")
                ]

                if text_files:
                    # Verwende die erste gefundene Textdatei
                    text_file = text_files[0]
                    with open(text_file, "r", encoding="utf-8") as f:
                        photo_description = f.read().strip()

                    # Falls die Textdatei leer ist, verwende den Dateinamen (ohne Erweiterung)
                    if not photo_description:
                        photo_description = os.path.splitext(os.path.basename(text_file))[0]

                # Generiere den Ausgabe-Pfad basierend auf dem Ordnernamen
                output_file_name = f"collage_{folder}.jpg"
                output_path = os.path.join(self.outputDir, output_file_name)

                # Collage generieren
                print(f"Generiere Collage für Ordner: {folder}")
                date = self.startDate + timedelta(weeks=weekIndex)
                self.generate_collage(image_files, date, output_path, photo_description)


if __name__ == "__main__":
    colGen = CollageGenerator()
    colGen.generateWeekCollages()

