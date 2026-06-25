import pytest
from PIL import Image, ImageDraw, ImageFont

from Photo_Composition_Designer.image.CollageRenderer import CollageRenderer

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


# ────────────────────────────────────────────────────────────────
# Helper: Create a colored test image with centered text
# ────────────────────────────────────────────────────────────────
def create_test_image(idx: int, orientation: str) -> Image.Image:
    """
    Creates a synthetic image with a number and orientation label centered.
    """
    if orientation == "L":
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

    draw.text(
        (size[0] / 1.5, size[1] / 2),
        label,
        fill=(255, 255, 255),
        font=font,
        anchor="rt",
    )

    return img


# ────────────────────────────────────────────────────────────────
# Layout configurations from your draft
# ────────────────────────────────────────────────────────────────
group_6 = ["L", "L", "L", "P", "P", "P"]
group_9 = ["L", "L", "L", "P", "L", "P", "P", "P", "P"]
group_11 = ["L", "L", "L", "P", "L", "P", "L", "P", "P", "P", "P"]
layout_configurations = [
    (1, ["L"]),
    (1, ["P"]),
    (2, ["L", "L"]),
    (2, ["P", "P"]),
    (2, ["L", "P"]),
    (3, ["L", "L", "L"]),
    (3, ["P", "P", "P"]),
    (3, ["L", "L", "P"]),
    (3, ["L", "P", "P"]),
    (4, ["L", "L", "L", "L"]),
    (4, ["L", "L", "L", "P"]),
    (4, ["L", "L", "P", "P"]),
    (4, ["L", "P", "P", "P"]),
    (5, ["L", "L", "L", "L", "L"]),
    (5, ["L", "L", "L", "L", "P"]),
    (5, ["L", "L", "L", "P", "P"]),
    (5, ["L", "L", "P", "P", "P"]),
    (6, group_6),
    (6, ["L", "L", "L", "L", "P", "P"]),
    (6, ["L", "L", "L", "L", "L", "L"]),
    (6, ["P", "P", "P", "P", "P", "P"]),
    (7, ["L", "L", "L", "P", "P", "P", "P"]),
    (9, group_9),
    (11, group_11),
    (20, group_9 + group_11),
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
    L_images = [create_test_image(i, "L") for i in range(1, 20)]
    P_images = [create_test_image(i, "P") for i in range(1, 20)]

    if not L_images or not P_images:
        pytest.skip("Both L and P test images required.")

    # Select images as defined in layout spec
    selected_images = []
    L_ptr = 0
    P_ptr = 0

    for t in layout:
        if t == "L":
            selected_images.append(L_images[L_ptr])
            L_ptr += 1
        else:
            selected_images.append(P_images[P_ptr])
            P_ptr += 1

    assert len(selected_images) == num_images

    generator = CollageRenderer(width=500, height=300, spacing=10, color=(200, 200, 0))

    # RUN THE COLLAGE GENERATOR
    collage = generator.generate(selected_images)

    # Basic validation
    assert collage is not None
    assert isinstance(collage, Image.Image)
    assert collage.size == (generator.width, generator.height)
    assert collage.mode == "RGB"

    # Optionally save for debugging:
    collage.save(temp_dir / f"{num_images}_{'_'.join(layout)}.jpg")
