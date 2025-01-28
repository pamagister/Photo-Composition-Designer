import os

from PIL import Image

from common.config import Config
from snapcalendar.collage.calendarGenerator import CalendarGenerator
from snapcalendar.collage.descriptionGenerator import DescriptionGenerator
from snapcalendar.collage.mapGenerator import MapGenerator
from snapcalendar.collage.photoLayoutManager import PhotoLayoutManager


class CollageGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.photoDirectory = self.config.photoDirectory
        self.outputDir = self.photoDirectory + '/collages'
        os.makedirs(self.outputDir, exist_ok=True)
        self.calendar_height = self.config.calendarHeight
        self.width = self.config.width
        self.height = self.config.height
        self.spacing = self.config.spacing
        self.calendarObj = CalendarGenerator(self.config)
        self.descGenerator = DescriptionGenerator()
        self.mapGenerator = MapGenerator()
        self.layoutManager = None

    def generate_collage(self, image_files, week, output_path, photo_description=''):
        """
        Erzeugt eine Collage mit Bildern, einem Calendarium und einer Europakarte mit Foto-Locations.
        """
        collage = Image.new("RGB", (self.width, self.height), self.config.backgroundColor)
        calendarImage = self.calendarObj.generateCalendarium(week)
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

                # Generiere den Ausgabe-Pfad basierend auf dem Ordnernamen
                output_file_name = f"collage_{folder}.jpg"
                output_path = os.path.join(self.outputDir, output_file_name)

                # Collage generieren
                print(f"Generiere Collage für Ordner: {folder}")
                self.generate_collage(image_files, weekIndex + 30, output_path)


def generateDifferentLayouts():
    """
    Testfunktion: Generiert Collagen mit verschiedenen Layouts und Bildkombinationen
    aus dem Ordner ../res/images.
    """

    collageGen = CollageGenerator()
    base_dir = collageGen.photoDirectory
    output_dir = collageGen.outputDir
    # Sammle alle Bilddateien (auf oberster Ebene)
    image_files = [
        os.path.join(base_dir, file)
        for file in sorted(os.listdir(base_dir))
        if file.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    if not image_files:
        print(f"Keine Bilder in {base_dir} gefunden. Abbruch.")
        return

    # Trenne Bilder in landscape und portrait basierend auf Dateinamen
    landscape_images = [f for f in image_files if "landscape" in os.path.basename(f).lower()]
    portrait_images = [f for f in image_files if "portrait" in os.path.basename(f).lower()]

    if not landscape_images or not portrait_images:
        print("Es werden sowohl 'landscape'- als auch 'portrait'-Bilder benötigt.")
        return

    print("Starte Generierung von Collagen mit verschiedenen Layouts...")

    layout_configurations = [
        (1, ["landscape"]),  # 1 Bild: 1x landscape
        (1, ["portrait"]),  # 1 Bild: 1x portrait
        (2, ["landscape", "landscape"]),  # 2 Bilder: 2x landscape
        (2, ["portrait", "portrait"]),  # 2 Bilder: 2x portrait
        (2, ["landscape", "portrait"]),  # 2 Bilder: 1x landscape, 1x portrait
        (3, ["landscape", "landscape", "landscape"]),  # 3 Bilder: 3x landscape
        (3, ["portrait", "portrait", "portrait"]),  # 3 Bilder: 3x portrait
        (3, ["landscape", "landscape", "portrait"]),  # 3 Bilder: 2x landscape, 1x portrait
        (3, ["landscape", "portrait", "portrait"]),  # 3 Bilder: 1x landscape, 2x portrait
        (4, ["landscape", "landscape", "landscape", "landscape"]),  # 4 Bilder: 4x landscape
        (4, ["landscape", "landscape", "landscape", "portrait"]),  # 4 Bilder: 3x landscape, 1x portrait
        (4, ["landscape", "landscape", "portrait", "portrait"]),  # 4 Bilder: 2x landscape, 2x portrait
        (4, ["landscape", "portrait", "portrait", "portrait"]),  # 4 Bilder: 1x landscape, 3x portrait
        (5, ["landscape", "landscape", "landscape", "landscape", "landscape"]),  # 5 Bilder: 5x landscape
        (5, ["landscape", "landscape", "landscape", "landscape", "portrait"]),  # Beispiele für 5 Bilder
        (5, ["landscape", "landscape", "landscape", "portrait", "portrait"]),  # Beispiele für 5 Bilder
        (5, ["landscape", "landscape", "portrait", "portrait", "portrait"]),  # Beispiele für 5 Bilder
        (6, ["landscape", "landscape", "landscape", "portrait", "portrait", "portrait"]),  # Beispiele für 6 Bilder
    ]


    for index, (num_images, layout) in enumerate(layout_configurations):
        # Wähle Bilder basierend auf Layout
        landscape_pointer = 0
        portrait_pointer = 0
        selected_images = []
        for img_type in layout:
            if img_type == "landscape" and landscape_images:
                selected_images.append(landscape_images[landscape_pointer])
                landscape_pointer += 1
            elif img_type == "portrait" and portrait_images:
                selected_images.append(portrait_images[portrait_pointer])
                portrait_pointer += 1

        # Skip, wenn nicht genug Bilder für die Kombination vorhanden sind
        if len(selected_images) < num_images:
            print(f"Nicht genügend Bilder für Layout {layout}. Überspringe...")
            continue

        # Generiere den Ausgabe-Pfad
        output_file_name = f"collage_layout_{index + 1}.jpg"
        output_path = os.path.join(output_dir, output_file_name)

        # Collage generieren
        print(f"Generiere Collage für Layout: {layout}")
        collageGen.generate_collage(selected_images, index, output_path)


if __name__ == "__main__":
    if False:
        colGen = CollageGenerator()
        colGen.generateWeekCollages()
    else:
        generateDifferentLayouts()
