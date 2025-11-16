from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from Photo_Composition_Designer.common.Photo import Photo
from Photo_Composition_Designer.core.PhotoLayoutManager import PhotoLayoutManager


@pytest.fixture
def mock_images():
    """Erstellt eine Liste von Mock-Bildern."""

    def _mock_images(n):
        mock_image = MagicMock(spec=Image.Image)
        mock_image.size = (500, 300)  # Beispielgröße
        return [mock_image for _ in range(n)]

    return _mock_images


@pytest.fixture
def photo_layout():
    """Erstellt eine PhotoLayoutManager-Instanz mit einem Mock-Collage-Bild."""
    # mock_collage = MagicMock(spec=Image.Image)
    return PhotoLayoutManager()


@pytest.mark.parametrize("num_images", [1, 2, 3, 4, 5, 6, 7, 8])
@patch("PIL.Image.open", return_value=MagicMock(spec=Image.Image))
def test_arrange_images(mock_open, photo_layout, mock_images, num_images):
    """Testet arrangeImages mit verschiedenen Bildmengen."""

    mock_img_list = mock_images(num_images)
    orientations = ["landscape"] * num_images

    with (
        patch.object(PhotoLayoutManager, "sortByAspectRatio", return_value=mock_img_list),
        patch.object(PhotoLayoutManager, "analyzeImages", return_value=orientations),
        patch.object(PhotoLayoutManager, "arrangeOneImage") as mock_arrange_one,
        patch.object(PhotoLayoutManager, "arrangeTwoImages") as mock_arrange_two,
        patch.object(PhotoLayoutManager, "arrangeThreeImages") as mock_arrange_three,
        patch.object(PhotoLayoutManager, "arrangeFourImages") as mock_arrange_four,
        patch.object(PhotoLayoutManager, "arrangeFiveImages") as mock_arrange_five,
        patch.object(PhotoLayoutManager, "arrangeMultipleImages") as mock_arrange_multiple,
        patch.object(Path, "exists", return_value=True),
    ):
        image_paths = [f"img{i}.jpg" for i in range(num_images)]
        photos = [Photo(Path(filename)) for filename in image_paths]
        photo_layout.arrangeImages(photos)

        assert mock_open.call_count == num_images

        (
            mock_arrange_one.assert_called_once()
            if num_images == 1
            else mock_arrange_one.assert_not_called()
        )
        (
            mock_arrange_two.assert_called_once()
            if num_images == 2
            else mock_arrange_two.assert_not_called()
        )
        (
            mock_arrange_three.assert_called_once()
            if num_images == 3
            else mock_arrange_three.assert_not_called()
        )
        (
            mock_arrange_four.assert_called_once()
            if num_images == 4
            else mock_arrange_four.assert_not_called()
        )
        (
            mock_arrange_five.assert_called_once()
            if num_images == 5
            else mock_arrange_five.assert_not_called()
        )
        (
            mock_arrange_multiple.assert_called_once()
            if num_images >= 6
            else mock_arrange_multiple.assert_not_called()
        )
