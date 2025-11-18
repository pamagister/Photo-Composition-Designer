from pathlib import Path

import pytest
from PIL import Image

from Photo_Composition_Designer.image.MapGenerator import MapGenerator


@pytest.fixture
def temp_dir():
    """
    Creates a /temp directory at project root.
    """
    project_root = Path(__file__).resolve().parents[1]
    temp_dir = project_root / "temp"
    temp_dir.mkdir(exist_ok=True)
    return temp_dir


def test_generate_map_creates_image_file(temp_dir):
    """
    Generate a real map image and verify it is saved and readable.
    """
    gps_coordinates = [
        (51.0504, 13.7373),  # Dresden
        (51.3397, 12.3731),  # Leipzig
        (50.8278, 12.9214),  # Chemnitz
        (51.1079, 17.0441),  # Breslau
        (52.5200, 13.5156),  # Berlin
    ]

    map_gen = MapGenerator(mapHeight=200, mapWidth=200)

    img = map_gen.generate_map(gps_coordinates)

    # Save image to temp for verification
    output_path = temp_dir / "test_map_output.png"
    img.save(output_path)

    # Assertions
    assert output_path.exists(), "Generated map file does not exist."

    opened = Image.open(output_path)
    assert opened.size == (200, 200), f"Image has wrong size: {opened.size}"

    # Basic pixel check – ensures image is not empty/corrupt
    px = opened.getpixel((10, 10))
    assert isinstance(px, tuple), "Pixel data invalid, image may be corrupted."


def test_convert_to_decimal():
    """
    Simple unit test for decimal conversion.
    """
    map_gen = MapGenerator()

    # degrees, minutes, seconds
    dms = [10, 30, 30]  # 10° 30' 30''
    decimal = map_gen.convert_to_decimal(dms)

    expected = 10 + 30 / 60 + 30 / 3600
    assert pytest.approx(decimal, 0.0001) == expected
