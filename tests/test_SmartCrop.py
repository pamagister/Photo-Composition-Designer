from pathlib import Path

from PIL import Image

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.image.SmartCrop import SmartCrop

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


def test_smart_crop(temp_dir):
    """
    Tests the SmartCrop functionality, including object detection, smart cropping,
    and visualization of the crop process.
    """
    detector = ObjectDetector()
    cropper = SmartCrop()

    # Directories containing test images
    image_dirs = [
        Path("images/week_6_testimages_3"),
        Path("images/week_7_testimages_4"),
        Path("images/week_8_testimages_5"),
    ]

    # Define various target crop sizes/aspect ratios
    crop_sizes = [
        (300, 300),  # Square
        (500, 300),  # Moderate Landscape
        (300, 500),  # Moderate Portrait
        (800, 300),  # Very Wide Landscape
        (300, 800),  # Very High Portrait
        (600, 400),  # 3:2 Landscape
        (400, 600),  # 3:4 Portrait
    ]

    for image_dir in image_dirs:
        for image_file in sorted(image_dir.glob("*.jpg")):
            image = Image.open(image_file).convert("RGB")  # Ensure RGB for consistent processing

            detections = detector.detect(image)

            # Test various target formats
            for width, height in crop_sizes:
                # Perform the smart crop, getting both the cropped image and the crop box
                cropped_image, crop_box = cropper.crop(
                    image=image,
                    target_width=width,
                    target_height=height,
                    detections=detections,
                )

                assert cropped_image is not None
                assert cropped_image.size == (width, height)

                # Save the cropped image
                # cropped_image_name = f"{image_file.stem}_cropped_{width}x{height}.jpg"
                # cropped_image.save(temp_dir / cropped_image_name)

                # Generate and save the visualized image
                visualized_image = cropper.visualize_crop(
                    original_image=image,
                    detections=detections,
                    crop_box=crop_box,
                    output_max_dim=1080,  # Normalize long edge to HD for visualization
                )
                visualized_image_name = f"{image_file.stem}_visualized_{width}x{height}.jpg"
                visualized_image.save(temp_dir / visualized_image_name)

                print(f"Processed {image_file.name} for {width}x{height}. Saved to {temp_dir}")
