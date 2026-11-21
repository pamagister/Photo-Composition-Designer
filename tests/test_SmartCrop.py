"""Tests for smart cropping against the flat Pixabay fixture collection."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from photo_composition_designer.render.object_detector import ObjectDetector
from photo_composition_designer.render.smart_crop import SmartCrop

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")

CROP_SIZES = [
    (300, 300),
    (500, 300),
    (300, 500),
    (600, 400),
    (400, 600),
]


def test_smart_crop(yolo_model_path: Path, temp_dir):
    """Exercise smart crop over a representative sample of the fixture set."""
    detector = ObjectDetector(model_path=str(yolo_model_path))
    cropper = SmartCrop()

    image_files = sorted(Path("images").glob("*.jpg"))[:8]
    assert image_files, "expected at least one image in images/"

    for image_file in image_files:
        image = Image.open(image_file).convert("RGB")
        width, height = image.size
        output_max_dim = 1080
        if max(width, height) > output_max_dim:
            scale = output_max_dim / max(width, height)
            image = image.resize(
                (int(width * scale), int(height * scale)),
                Image.Resampling.LANCZOS,
            )

        detections = detector.detect(image)

        for target_width, target_height in CROP_SIZES:
            cropped_image, crop_box = cropper.crop(
                image=image,
                target_width=target_width,
                target_height=target_height,
                detections=detections,
            )
            assert cropped_image is not None
            assert cropped_image.size == (target_width, target_height)

            visualized_image = cropper.visualize_crop(
                original_image=image,
                detections=detections,
                crop_box=crop_box,
            )
            visualized_name = f"{image_file.stem}_visualized_{target_width}x{target_height}.jpg"
            visualized_image.save(temp_dir / visualized_name)
