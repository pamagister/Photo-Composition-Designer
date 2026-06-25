from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
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

    image_dir = Path("images/week_8_testimages_5")

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


def test_object_detector_caching(temp_dir):
    # Patch the onnxruntime InferenceSession so we don't run real model
    import onnxruntime as ort

    # Prepare a mock session that simulates one detection
    mock_session = MagicMock()
    mock_input = MagicMock()
    mock_input.name = "input"
    mock_session.get_inputs.return_value = [mock_input]
    # outputs format: [ array(shape=(1, N, 6)) ] -> outputs[0][0] yields detections
    mock_session.run = MagicMock(
        return_value=[np.array([[[10.0, 20.0, 100.0, 120.0, 0.9, 0.0]]], dtype=np.float32)]
    )

    # Replace constructor to return our mock session
    ort.InferenceSession = lambda *args, **kwargs: mock_session

    # Create detector using the test temp dir for persistent cache
    detector = ObjectDetector(confidence_threshold=0.5, cache_dir=temp_dir)
    detector.clear_cache()

    # Create a dummy image
    image_dir = Path("images/week_8_testimages_5")
    filename = "landscape_two_persons_right.jpg"
    dummy_image = Image.open(image_dir / filename)

    # First detection should invoke the ONNX session
    detector.detect(dummy_image)
    assert mock_session.run.call_count == 1

    # Second detector instance pointing to same cache dir should use filesystem cache
    detector2 = ObjectDetector(confidence_threshold=0.5, cache_dir=temp_dir)
    detector2.detect(dummy_image)
    # run should still have been called only once because the second call used cache
    assert mock_session.run.call_count == 1

    # Cache file must exist in temp_dir
    json_files = list(Path(temp_dir).glob("*.json"))
    assert len(json_files) >= 1

    # Clearing cache should remove cache files and cause subsequent detect to run again
    detector.clear_cache()
    assert not any(Path(temp_dir).glob("*.json"))

    # Calling detect with a fresh detector instance should trigger run again
    detector3 = ObjectDetector(confidence_threshold=0.5, cache_dir=temp_dir)
    detector3.detect(dummy_image)
    assert mock_session.run.call_count == 2
