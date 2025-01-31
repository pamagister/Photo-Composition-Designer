import os
from datetime import timedelta
from pathlib import Path

import pytest

from designer.CollageGenerator import CollageGenerator
from designer.common.Config import Config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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

    WEEK_COUNTER = 0

    def setup_method(self):
        type(self).WEEK_COUNTER += 1  # Greife direkt auf die Klassenvariable zu
        print(f"WEEK_COUNTER: {type(self).WEEK_COUNTER}")

    @pytest.mark.parametrize("num_images, layout", layout_configurations)
    def test_generate_different_layouts(self, num_images, layout):
        """
        Tests different layouts with CollageGenerator.
        """
        config_file = PROJECT_ROOT / 'config' / 'config.ini'
        config = Config(config_file)
        config.dpi = 50
        config.jpgQuality = 40
        collageGen = CollageGenerator(config)
        startDate = collageGen.startDate
        base_dir = os.path.join(collageGen.photoDirectory, 'layout_orientation')
        output_dir = collageGen.outputDir

        # Collect image files
        image_files = [
            os.path.join(base_dir, file)
            for file in sorted(os.listdir(base_dir))
            if file.lower().endswith((".png", ".jpg", ".jpeg"))
        ]

        if not image_files:
            pytest.skip(f"No pictures in {base_dir} found.")

        landscape_images = [f for f in image_files if "landscape" in os.path.basename(f).lower()]
        portrait_images = [f for f in image_files if "portrait" in os.path.basename(f).lower()]

        if not landscape_images or not portrait_images:
            pytest.skip("Both 'landscape' and 'portrait' images are required.")

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
            pytest.skip(f"Not enough images for layout {layout}. Skip...")

        # Generiere den Ausgabe-Pfad
        output_file_name = f"collage_layout_{num_images}_{'_'.join(layout)}.jpg"
        output_path = os.path.join(output_dir, output_file_name)

        # Collage generieren
        print(f"Generate collage for layout: {layout}")
        date = startDate + timedelta(weeks=self.WEEK_COUNTER)  # Variiere das Datum pro Test
        self.WEEK_COUNTER += 1
        collageGen.generate_collage(selected_images, date, output_path)

        assert os.path.exists(output_path), f"Output file was not created: {output_path}"

    def test_generate_from_folders(self):
        config = Config()
        config.photoDirectory = config.photoDirectory / 'layout_orientation'

        collageGen = CollageGenerator(config)
        collageGen.generateProjectFromImageFolder()
