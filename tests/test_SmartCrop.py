from pathlib import Path

from PIL import Image, ImageDraw

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.image.SmartCrop import SmartCrop

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


def test_smart_crop(temp_dir):

    detector = ObjectDetector()
    cropper = SmartCrop()

    image_dir = Path("images/testimages")

    crop_sizes = [
        (300, 300),  # square
        (500, 300),  # landscape
        (300, 500),  # portrait
        (800, 300),  # panorama
    ]

    for image_file in sorted(image_dir.glob("*.jpg")):
        image = Image.open(image_file)

        detections = detector.detect(image)

        # Original mit Bounding Boxen speichern
        debug = image.copy()

        draw = ImageDraw.Draw(debug)

        for detection in detections:
            draw.rectangle(
                detection.bbox,
                outline="red",
                width=4,
            )

            draw.text(
                (
                    detection.bbox[0],
                    max(0, detection.bbox[1] - 20),
                ),
                detection.class_name,
                fill="red",
            )

        debug.save(temp_dir / f"smartcrop_source_{image_file.name}")

        # Verschiedene Zielformate testen
        for width, height in crop_sizes:
            cropped = cropper.crop(
                image=image,
                target_width=width,
                target_height=height,
                detections=detections,
            )

            assert cropped is not None
            assert cropped.size == (width, height)

            cropped.save(temp_dir / (f"{image_file.stem}_{width}x{height}.jpg"))
