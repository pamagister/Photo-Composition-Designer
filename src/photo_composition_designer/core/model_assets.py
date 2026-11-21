"""Locations and download metadata for optional local model assets."""

from __future__ import annotations

import os
from pathlib import Path

from photo_composition_designer.core.appdata import data_dir

#: File name of the YOLO ONNX model used for object-aware cropping.
YOLO_MODEL_FILENAME = "yolo26n.onnx"

#: Official Ultralytics release asset for the downloadable YOLO model.
YOLO_MODEL_URL = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.onnx"

#: Environment variable that points callers at an explicit model file.
YOLO_MODEL_ENV = "PCD_YOLO_MODEL"


def default_yolo_model_path() -> Path:
    """Return the OS-specific default location for the YOLO ONNX model.

    The model is a downloaded asset rather than part of the source tree, so it
    lives under the user's data directory (``data_dir()/models``).
    """
    return data_dir() / "models" / YOLO_MODEL_FILENAME


def repository_yolo_model_path() -> Path:
    """Return the repository-local cache location used by development tests."""
    repository_root = Path(__file__).resolve().parents[3]
    return repository_root / ".cache" / "yolo" / YOLO_MODEL_FILENAME


def resolve_yolo_model_path() -> Path | None:
    """Return the first available YOLO model path, or ``None``.

    An explicit ``PCD_YOLO_MODEL`` override wins. Otherwise the repository-local
    test cache is preferred, followed by the per-user default location.
    """
    override = os.environ.get(YOLO_MODEL_ENV)
    if override:
        return Path(override).expanduser()

    repository_path = repository_yolo_model_path()
    if repository_path.is_file():
        return repository_path

    default_path = default_yolo_model_path()
    return default_path if default_path.is_file() else None
