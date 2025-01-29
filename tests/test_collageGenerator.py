from pathlib import Path

import pytest
from datetime import timedelta
import os

from snapcalendar.CollageGenerator import CollageGenerator
from tempfile import NamedTemporaryFile

from snapcalendar.common.Config import Config
from parameterized import parameterized


layout_configurations = [
    (1, ["landscape"]),
    (1, ["portrait"]),
    (2, ["landscape", "landscape"]),
    (2, ["portrait", "portrait"]),
    (2, ["landscape", "portrait"]),
    (3, ["landscape", "landscape", "landscape"]),
    (3, ["portrait", "portrait", "portrait"]),
    (3, ["landscape", "landscape", "portrait"]),
    (3, ["landscape", "portrait", "portrait"]),
    (4, ["landscape", "landscape", "landscape", "landscape"]),
    (4, ["landscape", "landscape", "landscape", "portrait"]),
    (4, ["landscape", "landscape", "portrait", "portrait"]),
    (4, ["landscape", "portrait", "portrait", "portrait"]),
    (5, ["landscape", "landscape", "landscape", "landscape", "landscape"]),
    (5, ["landscape", "landscape", "landscape", "landscape", "portrait"]),
    (5, ["landscape", "landscape", "landscape", "portrait", "portrait"]),
    (5, ["landscape", "landscape", "portrait", "portrait", "portrait"]),
    (6, ["landscape", "landscape", "landscape", "portrait", "portrait", "portrait"]),
    (7, ["landscape", "landscape", "landscape", "landscape", "portrait", "portrait", "portrait"]),
]


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
minimalExtension = 6         ; Range for map display (in degree)

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

    @pytest.mark.parametrize("num_images, layout", layout_configurations)
    def test_generate_different_layouts(self, sample_config_file, num_images, layout):
        """
        Testet verschiedene Layouts mit CollageGenerator.
        """

        config = Config(sample_config_file)
        collageGen = CollageGenerator(config)
        startDate = collageGen.startDate
        base_dir = os.path.join(collageGen.photoDirectory, 'layout_orientation')
        output_dir = collageGen.outputDir

        # Sammle Bilddateien
        image_files = [
            os.path.join(base_dir, file) for file in sorted(os.listdir(base_dir)) if file.lower().endswith((".png", ".jpg", ".jpeg"))
        ]

        if not image_files:
            pytest.skip(f"Keine Bilder in {base_dir} gefunden.")

        landscape_images = [f for f in image_files if "landscape" in os.path.basename(f).lower()]
        portrait_images = [f for f in image_files if "portrait" in os.path.basename(f).lower()]

        if not landscape_images or not portrait_images:
            pytest.skip("Sowohl 'landscape'- als auch 'portrait'-Bilder werden benötigt.")

        # Bilder für das Layout auswählen
        landscape_pointer = 0
        portrait_pointer = 0
        selected_images = []
        for img_type in layout:
            if img_type == "landscape" and landscape_pointer < len(landscape_images):
                selected_images.append(landscape_images[landscape_pointer])
                landscape_pointer += 1
            elif img_type == "portrait" and portrait_pointer < len(portrait_images):
                selected_images.append(portrait_images[portrait_pointer])
                portrait_pointer += 1

        # Skip, falls nicht genügend Bilder vorhanden sind
        if len(selected_images) < num_images:
            pytest.skip(f"Nicht genügend Bilder für Layout {layout}. Überspringe...")

        # Generiere den Ausgabe-Pfad
        output_file_name = f"collage_layout_{num_images}_{'_'.join(layout)}.jpg"
        output_path = os.path.join(output_dir, output_file_name)

        # Collage generieren
        print(f"Generiere Collage für Layout: {layout}")
        date = startDate + timedelta(weeks=len(layout))  # Variiere das Datum pro Test
        collageGen.generate_collage(selected_images, date, output_path)

        assert os.path.exists(output_path), f"Ausgabedatei wurde nicht erstellt: {output_path}"

    def test_generate_from_folders(self, sample_config_file):
        config = Config(sample_config_file)
        config.photoDirectory = config.photoDirectory / 'layout_orientation'

        collageGen = CollageGenerator(config)
        collageGen.generateProjectFromImageFolder()
