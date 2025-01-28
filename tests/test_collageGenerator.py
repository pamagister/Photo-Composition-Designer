from pathlib import Path

import pytest
from datetime import timedelta
import os

from snapcalendar.collageGenerator import CollageGenerator
from tempfile import NamedTemporaryFile

from snapcalendar.common.config import Config


class TestCollageGenerator:

    @pytest.fixture
    def sample_config_file(self):
        """
        Creates a temporary config.ini file with sample data.
        """
        data = """
        [GENERAL]
        photoDirectory = ../tests/images 
        								 
        [CALENDAR]                       
        language = de_DE                 
        holidayCountries = SN            
        startDate = 30.12.2024           
                                         
        [COLORS]                         
        backgroundColor = 20,20,20       
        textColor1 = 255,255,255         
        textColor2 = 150,150,150         
        holidayColor = 255,0,0           
                                         
        [GEO]                            
        usePhotoLocationMaps = True      
        photoLocationRange = 2.5         
                                         
        [SIZE]                           
        width = 1920                     
        height = 1280                    
        calendarHeight = 200             
        jpgQuality = 80                  
                                         
        [LAYOUT]                         
        fontSizeLarge = 0.4              
        fontSizeSmall = 0.15             
        fontSizeAnniversaries = 0.10     
        marginBottom = 30                
        marginSides = 10                 
        spacing = 10                     
        useShortDayNames = True          
        useShortMonthNames = True        
        usePhotoDescription = True       
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
