from pathlib import Path

from PIL import Image, ImageDraw

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


def test_object_detector(temp_dir):

    detector = ObjectDetector()

    images = {
        "landscape_one_bicycle_left.jpg": 1,
        "landscape_two_persons_right.jpg": 2,
        "portrait_one_person_top.jpg": 1,
        "portrait_two_cars_bottom.jpg": 2,
        "portrait_two_persons_bottom.jpg": 2,
    }

    image_dir = Path("images/testimages")

    for filename, expected in images.items():
        img = Image.open(image_dir / filename)

        detections = detector.detect(img)

        assert len(detections) >= expected

        draw = ImageDraw.Draw(img)

        for det in detections:
            draw.rectangle(
                det.bbox,
                outline="red",
                width=4,
            )

            draw.text(
                (det.bbox[0], det.bbox[1]),
                det.class_name,
                fill="red",
            )

        img.save(temp_dir / f"detector_{filename}")
