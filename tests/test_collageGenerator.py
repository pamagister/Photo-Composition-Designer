from pathlib import Path

import pytest
from datetime import timedelta
import os

from snapcalendar.CollageGenerator import CollageGenerator
from tempfile import NamedTemporaryFile

from snapcalendar.common.Config import Config


class TestCollageGenerator:

    @pytest.fixture
    def sample_config_file(self):
        """
        Creates a temporary config.ini file with sample data.
        """
        data = """
[GENERAL]
photoDirectory = ../tests/images  ; Path to the directory containing photos

[CALENDAR]
useCalendar = True               ; True: Calendar elements are generated. False if only a photo collage is wanted
language = de_DE                 ; Language for the calendar (e.g., de_DE, en_US)
holidayCountries = SN            ; Country/state codes for public holidays
startDate = 30.12.2024           ; Start date of the calendar

[COLORS]
backgroundColor = 20,20,20       ; Background color of the collage (RGB)
textColor1 = 255,255,255         ; Primary text color
textColor2 = 150,150,150         ; Secondary text color (e.g., for subtitles)
holidayColor = 255,0,0           ; Color for holidays

[GEO]
usePhotoLocationMaps = True      ; Use GPS data to generate maps
photoLocationRange = 2.5         ; Range for map display (in degree)

[SIZE]
width = 1920                     ; Width of the collage in pixels
height = 1280                    ; Height of the collage in pixels
calendarHeight = 200             ; Height of the calendar area in pixels
mapWidth = 230
mapHeight = 240
jpgQuality = 80                  ; JPG compression quality (1-100)

[LAYOUT]
fontSizeLarge = 0.4              ; Font size for large text (relative to image height)
fontSizeSmall = 0.15             ; Font size for small text
fontSizeAnniversaries = 0.10     ; Font size for anniversaries
marginBottom = 30                ; Bottom margin in pixels
marginSides = 10                 ; Side margins in pixels
spacing = 10                     ; Spacing between elements
useShortDayNames = True          ; Use short names for weekdays (e.g., Mon, Tue)
useShortMonthNames = True        ; Use short names for months (e.g., Jan, Feb)
usePhotoDescription = True       ; Include photo descriptions in the collage    
        """
        with NamedTemporaryFile("w", delete=False, suffix=".ini") as temp_file:
            temp_file.write(data)
            temp_file_path = temp_file.name
        yield temp_file_path
        Path(temp_file_path).unlink()  # Remove the file after the test

    def test_generate_different_layouts(self, sample_config_file):
        """
        Testfunktion: Generiert Collagen mit verschiedenen Layouts und Bildkombinationen
        aus dem Ordner ../tests/images.
        """
        config = Config(sample_config_file)
        collageGen = CollageGenerator(config)
        startDate = collageGen.startDate
        base_dir = os.path.join(collageGen.photoDirectory, 'layout_orientation')
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
            date = startDate + timedelta(weeks=index)
            collageGen.generate_collage(selected_images, date, output_path)

    def test_generate_from_folders(self, sample_config_file):
        config = Config(sample_config_file)
        config.photoDirectory = config.photoDirectory / 'layout_orientation'

        collageGen = CollageGenerator(config)
        collageGen.generateProjectFromImageFolder()
