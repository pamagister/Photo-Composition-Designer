import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from logging import Logger
from pathlib import Path

import numpy as np
import onnxruntime as ort
from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image


@dataclass(slots=True)
class Detection:
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]


class ObjectDetector:
    """
    YOLO ONNX wrapper.
    """

    # https://docs.ultralytics.com/datasets/segment/coco#sample-images-and-annotations
    # https://gist.github.com/rcland12/dc48e1963268ff98c8b2c4543e7a9be8
    WANTED_CLASSES = {
        0: "person",
        1: "bicycle",
        2: "car",
        3: "motorcycle",
        4: "airplane",
        5: "bus",
        6: "train",
        8: "boat",
        15: "cat",
        16: "dog",
        17: "horse",
        18: "sheep",
        19: "cow",
        32: "sports ball",
        39: "bottle",
        40: "wine glass",
        41: "cup",
    }

    def __init__(
        self,
        model_path: str = "res/yolo/yolo26n.onnx",
        confidence_threshold: float = 0.25,
        cache_dir: Path | str | None = None,
    ) -> None:
        """Create an ObjectDetector.

        Args:
            model_path: Path to the ONNX model.
            confidence_threshold: Minimum confidence for detections.
            cache_dir: Directory to store per-image cache JSON files. If None,
                a temp subfolder will be used.
        """
        initialize_logging()

        self.logger: Logger = get_logger("base")

        self.confidence_threshold = confidence_threshold

        # Initialize ONNX session
        self.session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )

        self.input_name = self.session.get_inputs()[0].name

        # In-memory per-process cache for speed
        self._memory_cache: dict[str, list[Detection]] = {}

        # Persistent cache directory
        if cache_dir is None:
            base = Path(tempfile.gettempdir()) / "photo_composition_detector_cache"
        else:
            base = Path(cache_dir)

        base.mkdir(parents=True, exist_ok=True)
        self.cache_dir: Path = base

    def detect(self, image: Image.Image) -> list[Detection]:
        # Compute a fast, stable fingerprint for the image and include the
        # current confidence threshold so that changes to the threshold
        # result in different cache entries.
        image_hash = self._compute_image_fingerprint(image)
        cache_key = f"{image_hash}-{self.confidence_threshold:.3f}"

        # Fast in-memory hit
        if cache_key in self._memory_cache:
            self.logger.debug(
                "Returning cached detections from memory for cache key: %s",
                cache_key,
            )
            return self._memory_cache[cache_key]

        # Check filesystem cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)

                detections = [self._detection_from_dict(d) for d in data]
                self._memory_cache[cache_key] = detections
                self.logger.debug(
                    "Returning cached detections from file for cache key: %s",
                    cache_key,
                )
                return detections
            except Exception as exc:  # narrow to IO/JSON errors is fine here
                self.logger.warning(
                    "Failed to read cache file %s (%s), performing detection",
                    cache_file,
                    exc,
                )

        self.logger.debug("Performing YOLO detection for cache key: %s", cache_key)

        orig_w, orig_h = image.size

        resized = image.resize((640, 640))

        img = np.asarray(resized, dtype=np.float32)
        img /= 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)

        outputs = self.session.run(
            None,
            {self.input_name: img},
        )

        detections = outputs[0][0]

        scale_x = orig_w / 640.0
        scale_y = orig_h / 640.0

        result: list[Detection] = []

        for det in detections:
            x1, y1, x2, y2, conf, cls_id = det

            cls_id = int(cls_id)

            if conf < self.confidence_threshold:
                continue

            if cls_id not in self.WANTED_CLASSES:
                continue

            class_name = self.WANTED_CLASSES[cls_id]

            self.logger.info(f"Object detected: {class_name}: {conf:.3f}")

            result.append(
                Detection(
                    class_name=class_name,
                    confidence=float(conf),
                    bbox=(
                        float(x1 * scale_x),
                        float(y1 * scale_y),
                        float(x2 * scale_x),
                        float(y2 * scale_y),
                    ),
                )
            )

        # Persist to filesystem (atomic write) and memory cache
        try:
            serial = [self._detection_to_dict(d) for d in result]
            tmp_path = cache_file.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(serial, fh, ensure_ascii=False)
            os.replace(tmp_path, cache_file)
        except Exception as exc:  # do not raise for cache write failures
            self.logger.warning("Failed to write cache file %s (%s)", cache_file, exc)

        self._memory_cache[cache_key] = result
        return result

    def clear_cache(self, key: str | None = None) -> None:
        """Clear the detector cache.

        If key is None, remove all cache files and clear in-memory cache.
        If key is provided, remove only the corresponding cache entry.
        """
        # Clear in-memory cache
        if key is None:
            self._memory_cache.clear()
        else:
            self._memory_cache.pop(key, None)

        # Clear filesystem cache
        try:
            if key is None:
                for file in self.cache_dir.glob("*.json"):
                    try:
                        file.unlink()
                    except Exception:
                        self.logger.debug("Failed to remove cache file %s", file)
            else:
                file = self.cache_dir / f"{key}.json"
                if file.exists():
                    try:
                        file.unlink()
                    except Exception:
                        self.logger.debug("Failed to remove cache file %s", file)
        except Exception as exc:
            self.logger.warning("Failed clearing cache in %s (%s)", self.cache_dir, exc)

    def _detection_to_dict(self, det: Detection) -> dict:
        """Serialize a Detection to a JSON-serializable dict."""
        return {
            "class_name": det.class_name,
            "confidence": float(det.confidence),
            "bbox": [float(x) for x in det.bbox],
        }

    def _detection_from_dict(self, data: dict) -> Detection:
        """Deserialize a dict into a Detection."""
        return Detection(
            class_name=str(data["class_name"]),
            confidence=float(data["confidence"]),
            bbox=tuple(float(x) for x in data["bbox"]),
        )

    def _compute_image_fingerprint(self, image: Image.Image) -> str:
        """Compute a fast fingerprint for an image.

        Strategy: convert to RGB, create a small thumbnail (32x32) and compute
        MD5 over the thumbnail bytes combined with the original image size to
        reduce collisions while remaining fast.
        """
        # Use a small thumbnail to be fast but robust. Prefer the LANCZOS
        # resampling filter when available; otherwise fall back to the
        # default resize implementation.
        thumb_size = (32, 32)
        img_copy = image.convert("RGB")
        if hasattr(Image, "Resampling"):
            thumb = img_copy.resize(thumb_size, Image.Resampling.LANCZOS)
        else:
            thumb = img_copy.resize(thumb_size)

        m = hashlib.md5()
        # include original size to reduce collisions for images with same
        # downsampled content
        m.update(f"{image.size[0]}x{image.size[1]}".encode())
        m.update(thumb.tobytes())
        return m.hexdigest()
