from pathlib import Path

from Photo_Composition_Designer.CompositionDesigner import CompositionDesigner
from Photo_Composition_Designer.config.config import ConfigParameterManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestCompositionDesigner:
    def test_generate_different_layouts(self):
        """
        Tests different collage layouts with CompositionDesigner.
        """

        # -----------------------------
        # Create light-weight config
        # -----------------------------
        config = ConfigParameterManager()

        # Override required values
        config.size.dpi.value = 150
        config.size.jpgQuality.value = 60

        # Photo input directory should be set in config
        base_photos_dir = PROJECT_ROOT / "images"
        config.general.photoDirectory.value = str(base_photos_dir)

        # -----------------------------
        # Initialize new CompositionDesigner
        # -----------------------------
        designer = CompositionDesigner(config)

        designer.generateProjectFromSubFolders()
