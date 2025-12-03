from pathlib import Path

from config_cli_gui.configtypes.color import Color
from config_cli_gui.configtypes.font import Font
from PIL import Image

from Photo_Composition_Designer.image.DescriptionRenderer import DescriptionRenderer


def test_generate_description_creates_image_in_temp():
    # Create a /temp folder in the project directory
    project_root = Path(__file__).resolve().parents[1]  # adjust if needed
    temp_dir = project_root / "temp"
    temp_dir.mkdir(exist_ok=True)

    # File path for manual inspection
    output_image_path = temp_dir / "test_description_output.png"
    font: Font = Font("DejaVuSans.ttf", 20, Color(111, 111, 111))
    # Prepare the generator
    generator = DescriptionRenderer(
        width_px=300,
        font=font,
        spacing_px=5,
        margin_side_px=10,
        background_color=(200, 255, 255),
    )

    # Generate an image
    img = generator.generate("Test123")

    # Save image for manual inspection later
    img.save(output_image_path)

    # Verify file exists
    assert output_image_path.exists(), "Generated image file was not created."

    # Verify it can be opened as a real image
    loaded_img = Image.open(output_image_path)
    loaded_img.verify()  # raises exception if corrupted

    # Verify expected dimensions based on constructor logic
    expected_height = int(20 + 5)
    assert loaded_img.width == 300
    assert loaded_img.height == expected_height
