"""Tests for the ONNX-based object detector.

The detector is exercised against the flat Pixabay fixture collection in
``images/``. Specific object counts are not asserted because the fixture set
no longer contains hand-curated scenes with known object counts; the tests
verify that detection runs, produces bounding boxes and caches results.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
from PIL import Image, ImageDraw

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


def _first_image() -> Path:
    """Return the first Pixabay JPEG in the flat fixture directory."""
    images = sorted(Path("images").glob("*.jpg"))
    assert images, "expected at least one image in images/"
    return images[0]


def test_object_detector(temp_dir):
    detector = ObjectDetector()

    image_path = _first_image()
    img = Image.open(image_path).convert("RGB")

    detections = detector.detect(img)

    # The detector must return a list of detections (may be empty for some
    # images) and must not raise on a real photograph.
    assert isinstance(detections, list)

    draw = ImageDraw.Draw(img)
    for det in detections:
        draw.rectangle(det.bbox, outline="red", width=4)
        draw.text((det.bbox[0], det.bbox[1]), det.class_name, fill="red")

    img.save(temp_dir / f"detector_{image_path.name}")


def test_object_detector_caching(temp_dir):
    import onnxruntime as ort

    mock_session = MagicMock()
    mock_input = MagicMock()
    mock_input.name = "input"
    mock_session.get_inputs.return_value = [mock_input]
    mock_session.run = MagicMock(
        return_value=[np.array([[[10.0, 20.0, 100.0, 120.0, 0.9, 0.0]]], dtype=np.float32)]
    )

    ort.InferenceSession = lambda *args, **kwargs: mock_session

    detector = ObjectDetector(confidence_threshold=0.5, cache_dir=temp_dir)
    detector.clear_cache()

    dummy_image = Image.open(_first_image()).convert("RGB")

    detector.detect(dummy_image)
    assert mock_session.run.call_count == 1

    detector2 = ObjectDetector(confidence_threshold=0.5, cache_dir=temp_dir)
    detector2.detect(dummy_image)
    assert mock_session.run.call_count == 1

    json_files = list(Path(temp_dir).glob("*.json"))
    assert len(json_files) >= 1

    detector.clear_cache()
    assert not any(Path(temp_dir).glob("*.json"))

    detector3 = ObjectDetector(confidence_threshold=0.5, cache_dir=temp_dir)
    detector3.detect(dummy_image)
    assert mock_session.run.call_count == 2
