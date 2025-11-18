import os
from datetime import timedelta
from pathlib import Path

import pytest

from Photo_Composition_Designer.common.Locations import Locations
from Photo_Composition_Designer.common.Photo import Photo
from Photo_Composition_Designer.CompositionDesigner import CompositionDesigner
from Photo_Composition_Designer.config.config import ConfigParameterManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


layout_configurations = [
    (1, ["landscape"]),
    (1, ["portrait"]),
    (2, ["landscape", "landscape"]),
    (2, ["portrait", "portrait"]),
    (2, ["landscape", "portrait"]),
    (3, ["landscape", "landscape", "landscape"]),
    (3, ["portrait", "portrait", "portrait"]),
    (3, ["portrait", "portrait", "portrait", "landscape"]),
]


class TestCompositionDesigner:
    WEEK_COUNTER = 0

    def setup_method(self):
        type(self).WEEK_COUNTER += 1
        print(f"WEEK_COUNTER: {type(self).WEEK_COUNTER}")

    @pytest.mark.parametrize("num_images, layout", layout_configurations)
    def test_generate_different_layouts(self, num_images, layout):
        """
        Tests different collage layouts with CompositionDesigner.
        """

        # -----------------------------
        # Create modern config
        # -----------------------------
        config = ConfigParameterManager()

        # Override required values
        config.size.dpi.value = 100
        config.size.jpgQuality.value = 20

        # Photo input directory should be set in config
        base_photos_dir = PROJECT_ROOT / "images" / "layout_orientation"
        config.general.photoDirectory.value = str(base_photos_dir)

        # -----------------------------
        # Initialize new CompositionDesigner
        # -----------------------------
        designer = CompositionDesigner(config)

        startDate = designer.startDate
        output_dir = designer.outputDir
        os.makedirs(output_dir, exist_ok=True)

        # -----------------------------
        # Collect images
        # -----------------------------
        if not base_photos_dir.exists():
            pytest.skip(f"Missing test folder: {base_photos_dir}")

        image_files = [
            f
            for f in sorted(os.listdir(base_photos_dir))
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        ]

        if not image_files:
            pytest.skip(f"No images found in {base_photos_dir}")

        landscape_images = [base_photos_dir / f for f in image_files if "landscape" in f.lower()]
        portrait_images = [base_photos_dir / f for f in image_files if "portrait" in f.lower()]

        if not landscape_images or not portrait_images:
            pytest.skip("Both landscape and portrait images required.")

        # Select images according to layout spec
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

        if len(selected_images) < num_images:
            pytest.skip(f"Not enough images for layout {layout}")

        # -----------------------------
        # Create output file path
        # -----------------------------
        output_file_name = f"collage_layout_{num_images}_{'_'.join(layout)}.jpg"
        output_path = output_dir / output_file_name

        # -----------------------------
        # Generate composition
        # -----------------------------
        print(f"Generate collage for layout: {layout}")

        date = startDate + timedelta(weeks=self.WEEK_COUNTER)
        self.WEEK_COUNTER += 1

        # After first test disable title page mode
        if self.WEEK_COUNTER > 1:
            designer.compositionTitle = ""
        locations = Locations()
        photos = [Photo(path, locations.locations_dict) for path in selected_images]

        description = f"This is a description for all {len(photos)} photos of week {date}"
        designer.generate_composition(photos, date, output_path, description)

        # -----------------------------
        # Validate test
        # -----------------------------
        assert output_path.exists(), f"Output file was not created: {output_path}"
