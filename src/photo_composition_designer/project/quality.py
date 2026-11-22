"""Deterministic image-quality heuristic for "best photos" selection.

The scorer is a pure function of an image file: it downsamples the image, then
combines a resolution score with a sharpness score derived from the variance of
a 3x3 Laplacian on the grayscale thumbnail. Both components are normalised to
``(0, 1]`` across a batch so the combined score is relative within the batch.

Results are cached per scorer instance by ``(path, mtime, file_size)`` so a
request that scores the same photos twice does not recompute them.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageFilter

#: Long edge used for the scoring thumbnail.
_THUMBNAIL_LONG_EDGE = 512

#: Initial weights for the combined quality score.
_RESOLUTION_WEIGHT = 0.6
_SHARPNESS_WEIGHT = 0.4

#: Score assigned to unreadable or missing images.
_MIN_SCORE = 1e-6


class QualityScorer:
    """Compute and cache a relative quality score for a batch of images."""

    def __init__(
        self,
        *,
        long_edge: int = _THUMBNAIL_LONG_EDGE,
        resolution_weight: float = _RESOLUTION_WEIGHT,
        sharpness_weight: float = _SHARPNESS_WEIGHT,
    ) -> None:
        self._long_edge = long_edge
        self._resolution_weight = resolution_weight
        self._sharpness_weight = sharpness_weight
        self._cache: dict[tuple[str, float, int], float] = {}

    def score_all(self, paths: dict[int, Path]) -> dict[int, float]:
        """Return a relative quality score for each photo id in ``paths``."""
        if not paths:
            return {}

        cache_keys: dict[int, tuple[str, float, int] | None] = {}
        raw_resolution: dict[int, float] = {}
        raw_sharpness: dict[int, float] = {}
        for photo_id, path in paths.items():
            key = self._cache_key(path)
            cache_keys[photo_id] = key
            if key is not None and key in self._cache:
                raw_resolution[photo_id] = self._cache[key]
                raw_sharpness[photo_id] = self._cache[key]
                continue
            resolution, sharpness = self._raw_scores(path)
            raw_resolution[photo_id] = resolution
            raw_sharpness[photo_id] = sharpness
            if key is not None:
                self._cache[key] = resolution

        resolution_norm = self._normalise(raw_resolution)
        sharpness_norm = self._normalise(raw_sharpness)
        return {
            photo_id: (
                self._resolution_weight * resolution_norm[photo_id]
                + self._sharpness_weight * sharpness_norm[photo_id]
            )
            for photo_id in paths
        }

    @staticmethod
    def _cache_key(path: Path) -> tuple[str, float, int] | None:
        """Return a ``(path, mtime, size)`` cache key or ``None`` when missing."""
        try:
            stat = path.stat()
        except OSError:
            return None
        return (str(path), stat.st_mtime, stat.st_size)

    @staticmethod
    def _normalise(values: dict[int, float]) -> dict[int, float]:
        """Scale values into ``(0, 1]`` using the batch minimum and maximum."""
        if not values:
            return {}
        lowest = min(values.values())
        highest = max(values.values())
        if math.isclose(lowest, highest):
            return dict.fromkeys(values, 1.0)
        span = highest - lowest
        return {key: (value - lowest) / span + _MIN_SCORE for key, value in values.items()}

    def _raw_scores(self, path: Path) -> tuple[float, float]:
        """Return the raw resolution and sharpness values for one image."""
        try:
            with Image.open(path) as image:
                image.load()
                width, height = image.size
                thumbnail = self._thumbnail(image)
                gray = thumbnail.convert("L")
        except (OSError, ValueError):
            return (0.0, 0.0)
        return (float(width * height), self._sharpness(gray))

    def _thumbnail(self, image: Image.Image) -> Image.Image:
        """Return a copy downscaled so its long edge is at most ``long_edge``."""
        if max(image.size) <= self._long_edge:
            return image.copy()
        ratio = self._long_edge / max(image.size)
        size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
        return image.resize(size, Image.Resampling.LANCZOS)

    @staticmethod
    def _sharpness(gray: Image.Image) -> float:
        """Return the variance of a 3x3 Laplacian on a grayscale thumbnail."""
        edges = gray.filter(
            ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=0)
        )
        pixels = list(edges.getdata())
        if not pixels:
            return 0.0
        mean = sum(pixels) / len(pixels)
        variance = sum((pixel - mean) ** 2 for pixel in pixels) / len(pixels)
        return variance


class SelectionScorer:
    """Combine object-detection importance with image quality."""

    def __init__(self, quality: dict[int, float]) -> None:
        self._quality = quality

    def score(self, photo_id: int, importance: float) -> float:
        """Return ``importance * quality`` for a photo.

        When quality is unknown for a photo, a neutral ``1.0`` is used so
        detection-only ranking remains well defined.
        """
        quality = self._quality.get(photo_id, 1.0)
        return importance * quality


__all__ = ["QualityScorer", "SelectionScorer"]
