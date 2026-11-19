from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageChops

from photo_composition_designer.render.map import MapRenderer

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


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

    map_gen = MapRenderer(
        mapHeight=200,
        mapWidth=200,
        minimalExtension=7,
        backgroundColor=(30, 30, 30),
        textColor1=(150, 250, 150),
    )

    img = map_gen.generate(gps_coordinates)

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


def test_empty_map_has_no_marker():
    map_gen = MapRenderer(
        mapHeight=120,
        mapWidth=160,
        minimalExtension=7,
        backgroundColor=(30, 30, 30),
        textColor1=(150, 250, 150),
    )

    image = map_gen.generate([]).convert("RGB")

    red_marker_pixels = [
        pixel for pixel in image.getdata() if pixel[0] > 200 and pixel[1] < 60 and pixel[2] < 60
    ]
    assert red_marker_pixels == []


def test_concurrent_map_renders_are_stable():
    def render():
        generator = MapRenderer(
            mapHeight=80,
            mapWidth=100,
            minimalExtension=7,
            backgroundColor=(30, 30, 30),
            textColor1=(150, 250, 150),
        )
        return generator.generate([(51.0504, 13.7373)])

    baseline = render()
    with ThreadPoolExecutor(max_workers=2) as pool:
        images = list(pool.map(lambda _: render(), range(2)))

    for image in images:
        assert ImageChops.difference(baseline, image).getbbox() is None
