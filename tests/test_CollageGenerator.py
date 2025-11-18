import pytest
from PIL import Image, ImageDraw, ImageFont

from Photo_Composition_Designer.image.CollageGenerator import CollageGenerator

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


# ────────────────────────────────────────────────────────────────
# Helper: Create a colored test image with centered text
# ────────────────────────────────────────────────────────────────
def create_test_image(idx: int, orientation: str) -> Image.Image:
    """
    Creates a synthetic image with a number and orientation label centered.
    """
    if orientation == "landscape":
        size = (300, 200)
        color = (100, 150, 240)
    else:
        size = (200, 300)
        color = (240, 150, 100)

    img = Image.new("RGB", size, color=color)
    draw = ImageDraw.Draw(img)

    label = f"{idx} {orientation}"

    # Load default font
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 20)
    except OSError:
        font = ImageFont.load_default()

    draw.text((size[0] / 1.5, size[1] / 2), label, fill=(255, 255, 255), font=font, anchor="rt")

    return img


# ────────────────────────────────────────────────────────────────
# Layout configurations from your draft
# ────────────────────────────────────────────────────────────────
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
    (
        7,
        [
            "landscape",
            "landscape",
            "landscape",
            "landscape",
            "portrait",
            "portrait",
            "portrait",
        ],
    ),
]


# ────────────────────────────────────────────────────────────────
# Main parameterized test
# ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("num_images, layout", layout_configurations)
def test_generate_different_layouts(num_images, layout, temp_dir):
    """
    Creates mock images of correct orientation and tests all layout variants
    with CollageGenerator.generate_collage().
    """

    # Create pools of test images
    landscape_images = [create_test_image(i, "landscape") for i in range(1, 10)]
    portrait_images = [create_test_image(i, "portrait") for i in range(1, 10)]

    if not landscape_images or not portrait_images:
        pytest.skip("Both landscape and portrait test images required.")

    # Select images as defined in layout spec
    selected_images = []
    landscape_ptr = 0
    portrait_ptr = 0

    for t in layout:
        if t == "landscape":
            selected_images.append(landscape_images[landscape_ptr])
            landscape_ptr += 1
        else:
            selected_images.append(portrait_images[portrait_ptr])
            portrait_ptr += 1

    assert len(selected_images) == num_images

    generator = CollageGenerator(width=500, height=300, spacing=10, color=(30, 30, 30))

    # RUN THE COLLAGE GENERATOR
    collage = generator.generate_collage(selected_images)

    # Basic validation
    assert collage is not None
    assert isinstance(collage, Image.Image)
    assert collage.size == (generator.width, generator.height)
    assert collage.mode == "RGB"

    # Optionally save for debugging:
    collage.save(temp_dir / f"collage_{num_images}_{'_'.join(layout)}.jpg")
