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

from photo_composition_designer.render.object_detector import ObjectDetector

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


def _first_image() -> Path:
    """Return the first Pixabay JPEG in the flat fixture directory."""
    images = sorted(Path("images").glob("*.jpg"))
    assert images, "expected at least one image in images/"
    return images[0]


def test_object_detector(yolo_model_path: Path, temp_dir):
    detector = ObjectDetector(model_path=str(yolo_model_path))

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
    model_path = str(Path(temp_dir) / "model.onnx")

    detector = ObjectDetector(model_path=model_path, confidence_threshold=0.5, cache_dir=temp_dir)
    detector.clear_cache()

    dummy_image = Image.open(_first_image()).convert("RGB")

    detector.detect(dummy_image)
    assert mock_session.run.call_count == 1

    detector2 = ObjectDetector(model_path=model_path, confidence_threshold=0.5, cache_dir=temp_dir)
    detector2.detect(dummy_image)
    assert mock_session.run.call_count == 1

    json_files = list(Path(temp_dir).glob("*.json"))
    assert len(json_files) >= 1

    detector.clear_cache()
    assert not any(Path(temp_dir).glob("*.json"))

    detector3 = ObjectDetector(model_path=model_path, confidence_threshold=0.5, cache_dir=temp_dir)
    detector3.detect(dummy_image)
    assert mock_session.run.call_count == 2


def test_fingerprint_is_stable_and_full_image():
    """The fingerprint is deterministic and covers the whole image (P1-W03)."""
    from photo_composition_designer.render.object_detector import compute_image_fingerprint

    image = Image.new("RGB", (200, 150), (10, 20, 30))
    assert compute_image_fingerprint(image) == compute_image_fingerprint(image)

    # Same size but different content must produce a different fingerprint.
    changed = Image.new("RGB", (200, 150), (10, 20, 30))
    for x in range(0, 60):
        for y in range(0, 60):
            changed.putpixel((x, y), (250, 250, 250))
    assert compute_image_fingerprint(changed) != compute_image_fingerprint(image)

    # A different size must also change the fingerprint.
    resized = image.resize((201, 150))
    assert compute_image_fingerprint(resized) != compute_image_fingerprint(image)


def test_fingerprint_detects_change_outside_centre():
    """A same-size edit away from the centre changes the fingerprint.

    This guards against a crop-based fingerprint that would reuse detections for
    photos that differ only outside a sampled region.
    """
    from photo_composition_designer.render.object_detector import compute_image_fingerprint

    base = Image.new("RGB", (300, 200), (0, 0, 0))
    edited = base.copy()
    draw = ImageDraw.Draw(edited)
    # Paint a block in the bottom-right corner, far from the centre.
    draw.rectangle((240, 150, 299, 199), fill=(255, 255, 255))

    assert compute_image_fingerprint(base) != compute_image_fingerprint(edited)
