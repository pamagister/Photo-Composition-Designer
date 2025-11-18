from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from Photo_Composition_Designer.common.Photo import Photo

EXAMPLE_IMAGE_1 = Path(__file__).parent.parent / "images" / "week_4" / "image_08.jpg"
EXAMPLE_IMAGE_2 = Path(__file__).parent.parent / "images" / "week_4" / "image_09.jpg"
EXAMPLE_IMAGE_5 = Path(__file__).parent.parent / "images" / "week_4" / "image_10.jpg"
TEST_DATE = datetime(2023, 5, 17, 14, 30, 25)
TEST_DATE_NO_TIME = datetime(2023, 5, 17, 12, 0, 0)


@pytest.mark.parametrize(
    "filename, expected_date",
    [
        ("20230517_143025.jpg", datetime(2023, 5, 17, 14, 30, 25)),
        ("IMG_20230517-143025.jpeg", datetime(2023, 5, 17, 14, 30, 25)),
        ("IMG_20230517.jpeg", datetime(2023, 5, 17, 12, 0, 0)),
        ("IMG_20230517_143025_sometext.jpeg", datetime(2023, 5, 17, 14, 30, 25)),
        ("IMG_20230517_Holiday.jpg", datetime(2023, 5, 17, 12, 0, 0)),
        ("03-2023-05-17-143025_002-strange_format.jpg", datetime(2023, 5, 17, 14, 30, 25)),
        ("random_name.jpg", datetime.max),
    ],
)
def test_extract_date_from_filename(filename, expected_date):
    """Testet die Extraktion von Datum aus Dateinamen mit Mocking."""

    with patch.object(
        Path, "exists", return_value=True
    ):  # Mockt exists(), damit keine echte Datei nötig ist
        photo = Photo(Path("dummy_path.jpg"))  # Normal initialisieren

    # Mock das file_path-Attribut direkt
    photo.file_path = MagicMock(spec=Path)
    photo.file_path.name = filename  # Setze den Namen der Datei

    # Führe die Methode aus und überprüfe das Ergebnis
    result = photo._extract_date_from_filename()

    assert result == expected_date


def test_file_not_found():
    """Testet, ob eine Exception geworfen wird, wenn die Datei nicht existiert."""
    with pytest.raises(FileNotFoundError):
        Photo(Path("non_existent_image.jpg"))


def test_get_image():
    """Testet, ob das Image-Objekt korrekt zurückgegeben wird."""
    photo = Photo(EXAMPLE_IMAGE_1)
    img = photo.get_image()
    assert isinstance(img, Image.Image)


def test_get_location():
    """Testet, ob die GPS-Koordinaten korrekt ausgelesen werden."""
    photo = Photo(EXAMPLE_IMAGE_2)
    gps = photo.get_location()
    assert gps is None or (isinstance(gps, tuple) and len(gps) == 2)


def test_get_date_exif():
    """Testet, ob das Datum korrekt aus den EXIF-Daten ausgelesen wird."""
    photo = Photo(EXAMPLE_IMAGE_2)
    date = photo.get_date()
    assert date == datetime(2023, 7, 31, 18, 54, 56)
