from pathlib import Path

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.base import CompositionDesigner

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
        config.size.dpi.value = 30
        config.size.jpgQuality.value = 20

        # Photo input directory should be set in config
        base_photos_dir = PROJECT_ROOT / "images"
        config.general.photoDirectory.value = str(base_photos_dir)

        # -----------------------------
        # Initialize new CompositionDesigner
        # -----------------------------
        designer = CompositionDesigner(config)

        designer.generate_compositions_from_folders()
