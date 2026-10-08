from pathlib import Path
from unittest.mock import Mock, call

import pytest
from PIL import Image

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.core.base import CompositionDesigner
from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestCompositionDesigner:
    @pytest.fixture
    def mock_config(self):
        """Fixture to provide a mock ConfigParameterManager."""
        config = ConfigParameterManager(persist_last_used=False)
        # Set default values for relevant config parameters
        config.size.dpi.value = 300
        config.size.width.value = 210  # A4 width in mm
        config.size.height.value = 297  # A4 height in mm
        config.size.calendarHeight.value = 20  # mm
        config.general.compositionTitle.value = ""
        config.general.photoDirectory.value = str(PROJECT_ROOT / "images")
        config.layout.marginTop.value = 10  # mm
        config.layout.marginBottom.value = 10  # mm
        config.layout.marginSides.value = 10  # mm
        config.layout.usePhotoDescription.value = True
        config.calendar.useCalendar.value = True
        config.geo.usePhotoLocationMaps.value = (
            True  # This affects calendar width, but not height directly
        )
        return config

    @pytest.fixture
    def designer_instance(self, mock_config):
        """Fixture to provide a CompositionDesigner instance with a mock config."""
        designer = CompositionDesigner(mock_config)
        # Mock descGenerator.height if it's accessed
        designer.descGenerator = DescriptionRenderer.from_config(mock_config)
        designer.descGenerator.height_px = designer._mm_to_px(
            mock_config.size.calendarHeight.value // 4
        )
        return designer

    def test_process_photo_description(self, designer_instance):
        """
        Tests the _process_photo_description method for various tag combinations.
        """
        # Scenario 1: No tags
        desc, no_cal, no_desc = designer_instance._process_photo_description("Normal description")
        assert desc == "Normal description"
        assert not no_cal
        assert not no_desc

        # Scenario 2: [no-calendar] tag
        desc, no_cal, no_desc = designer_instance._process_photo_description(
            "Description [no-calendar]"
        )
        assert desc == "Description"
        assert no_cal
        assert not no_desc

        # Scenario 3: [no-description] tag
        desc, no_cal, no_desc = designer_instance._process_photo_description(
            "Description [no-description]"
        )
        assert desc == "Description"
        assert not no_cal
        assert no_desc

        # Scenario 4: Both tags
        desc, no_cal, no_desc = designer_instance._process_photo_description(
            "Description [no-calendar] [no-description]"
        )
        assert desc == "Description"
        assert no_cal
        assert no_desc

        # Scenario 5: Empty description after tag removal
        desc, no_cal, no_desc = designer_instance._process_photo_description(
            "[no-calendar] [no-description]"
        )
        assert desc == ""
        assert no_cal
        assert no_desc  # Should be True because description is empty

        # Scenario 6: Empty description initially
        desc, no_cal, no_desc = designer_instance._process_photo_description("")
        assert desc == ""
        assert not no_cal
        assert no_desc  # Should be True because description is empty

        # Scenario 7: Description with leading/trailing spaces and tags
        desc, no_cal, no_desc = designer_instance._process_photo_description(
            "  Another description  [no-calendar] "
        )
        assert desc == "Another description"
        assert no_cal
        assert not no_desc

    def test_get_available_collage_height_px(self, designer_instance, mock_config):
        """
        Tests the get_available_collage_height_px method under various conditions.
        """
        # Calculate expected total height and margins in pixels
        total_height_px = designer_instance._mm_to_px(mock_config.size.height.value)
        margin_top_px = designer_instance._mm_to_px(mock_config.layout.marginTop.value)
        margin_bottom_px = designer_instance._mm_to_px(mock_config.layout.marginBottom.value)
        calendar_height_px = designer_instance._mm_to_px(mock_config.size.calendarHeight.value)
        desc_height_px = designer_instance.descGenerator.height_px  # Mocked value

        base_available_height = total_height_px - margin_top_px - margin_bottom_px

        # Scenario 1: Default (calendar and description enabled)
        expected_height = base_available_height - calendar_height_px - desc_height_px
        assert designer_instance.get_available_collage_height_px(False, False) == max(
            0, int(expected_height)
        )

        # Scenario 2: no_calendar_flag = True
        expected_height = base_available_height - desc_height_px
        assert designer_instance.get_available_collage_height_px(True, False) == max(
            0, int(expected_height)
        )

        # Scenario 3: no_description_flag = True
        expected_height = base_available_height - calendar_height_px
        assert designer_instance.get_available_collage_height_px(False, True) == max(
            0, int(expected_height)
        )

        # Scenario 4: Both flags True
        expected_height = base_available_height
        assert designer_instance.get_available_collage_height_px(True, True) == max(
            0, int(expected_height)
        )

        # Scenario 5: Config - useCalendar.value = False
        mock_config.calendar.useCalendar.value = False
        expected_height = base_available_height - desc_height_px
        assert designer_instance.get_available_collage_height_px(False, False) == max(
            0, int(expected_height)
        )
        mock_config.calendar.useCalendar.value = True  # Reset

        # Scenario 6: Config - usePhotoDescription.value = False
        mock_config.layout.usePhotoDescription.value = False
        expected_height = base_available_height - calendar_height_px
        assert designer_instance.get_available_collage_height_px(False, False) == max(
            0, int(expected_height)
        )
        mock_config.layout.usePhotoDescription.value = True  # Reset

        # Scenario 7: compositionTitle is present (should reduce height like calendar)
        mock_config.general.compositionTitle.value = "My Title"
        expected_height = base_available_height - calendar_height_px - desc_height_px
        assert designer_instance.get_available_collage_height_px(False, False) == max(
            0, int(expected_height)
        )
        mock_config.general.compositionTitle.value = ""  # Reset

    def test_generate_different_layouts(self):
        """
        Tests different collage layouts with CompositionDesigner.
        """

        # -----------------------------
        # Create light-weight config
        # -----------------------------
        config = ConfigParameterManager(persist_last_used=False)

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

    def test_batch_generation_scans_photo_folders_once(
        self, designer_instance, mock_config, monkeypatch
    ):
        mock_config.layout.generatePdf.value = False
        folder_names = ["week-1", "week-2"]
        folder_scan = Mock(return_value=folder_names)
        generate_folder = Mock(return_value=Image.new("RGB", (1, 1)))
        save_composition = Mock()
        monkeypatch.setattr(designer_instance.file_io, "get_photo_folders", folder_scan)
        monkeypatch.setattr(designer_instance, "_generate_composition_from_folder", generate_folder)
        monkeypatch.setattr(designer_instance, "save", save_composition)

        designer_instance.generate_compositions_from_folders()

        folder_scan.assert_called_once_with()
        assert generate_folder.call_args_list[0].args == ("week-1", 0)
        assert generate_folder.call_args_list[1].args == ("week-2", 1)
        assert save_composition.call_count == 2

    def test_batch_generation_reports_progress(self, designer_instance, mock_config, monkeypatch):
        mock_config.layout.generatePdf.value = False
        monkeypatch.setattr(
            designer_instance.file_io, "get_photo_folders", Mock(return_value=["week-1", "week-2"])
        )
        monkeypatch.setattr(
            designer_instance,
            "_generate_composition_from_folder",
            Mock(return_value=Image.new("RGB", (1, 1))),
        )
        monkeypatch.setattr(designer_instance, "save", Mock())
        progress_callback = Mock()
        designer_instance.progress_callback = progress_callback

        designer_instance.generate_compositions_from_folders()

        assert progress_callback.call_args_list == [call(0, 2), call(1, 2), call(2, 2)]

    def test_batch_generation_propagates_render_errors(
        self, designer_instance, mock_config, monkeypatch
    ):
        mock_config.layout.generatePdf.value = False
        monkeypatch.setattr(
            designer_instance.file_io, "get_photo_folders", Mock(return_value=["week-1"])
        )
        monkeypatch.setattr(
            designer_instance,
            "_generate_composition_from_folder",
            Mock(side_effect=RuntimeError("render failed")),
        )
        progress_callback = Mock()
        designer_instance.progress_callback = progress_callback

        with pytest.raises(RuntimeError, match="render failed"):
            designer_instance.generate_compositions_from_folders()

        assert progress_callback.call_args_list == [call(0, 1)]
