"""Content importance weighting for automatic collage layouts.

The automatic layout engine accepts a per-photo importance value that biases
cell areas toward photos with more relevant content. This module turns the
existing YOLO detections into that value without changing the rendering path.

Scoring is deliberately simple and bounded:

``importance = 1 + min(score, cap) * image_score_factor``

where ``score`` is the sum of confidences for the classes the product cares
about (``person``, ``cat``, ``dog``, ``horse``, ``cow`` and ``bird``). A cap
prevents a single busy photo from dominating the page. When the detector or the
model is unavailable, or the configured factor is zero, the neutral value
``1.0`` is returned so automatic layouts always work.

Scores are cached in memory by the photo digest. The detector keeps its own
in-memory and on-disk detection cache, so repeated layouts of the same photos
do not rerun inference.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from photo_composition_designer.io.media import resolve_source_path
from photo_composition_designer.project.models import PhotoAsset
from photo_composition_designer.project.repositories import SourceRootRepository
from photo_composition_designer.render.object_detector import (
    ObjectDetector,
    compute_image_fingerprint,
)

#: Detection classes that make a photo more important for the collage.
IMPORTANT_CLASSES = frozenset({"person", "cat", "dog", "horse", "cow", "bird"})

#: Upper bound applied to the summed detection confidence before scaling.
IMPORTANCE_CAP = 3.0

#: Neutral importance used when weighting is unavailable.
NEUTRAL_IMPORTANCE = 1.0


class ImportanceScorer:
    """Map photos to bounded importance values using an optional detector."""

    def __init__(
        self,
        detector: ObjectDetector | None,
        image_score_factor: float,
        *,
        cap: float = IMPORTANCE_CAP,
    ) -> None:
        """Create a scorer.

        Args:
            detector: Optional configured object detector. ``None`` disables
                weighting and yields neutral importance for every photo.
            image_score_factor: Project layout factor from
                ``LayoutProfile.image_score_factor``.
            cap: Maximum summed confidence that contributes to the score.
        """
        self._detector = detector
        self._image_score_factor = image_score_factor
        self._cap = cap
        self._cache: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        """Return whether weighting can produce non-neutral values."""
        return self._detector is not None and self._image_score_factor > 0.0

    def score_photos(
        self,
        connection: sqlite3.Connection,
        photos: list[PhotoAsset],
    ) -> list[float]:
        """Return one importance value per photo, aligned with the input order.

        Photos whose source file cannot be resolved or read fall back to the
        neutral value. The result never raises for an unavailable model; a
        detector failure is logged and treated as neutral.
        """
        if not self.enabled:
            return [NEUTRAL_IMPORTANCE] * len(photos)

        roots = SourceRootRepository(connection).get_many(
            [photo.source_root_id for photo in photos]
        )
        scores: list[float] = []
        for photo in photos:
            root = roots.get(photo.source_root_id)
            if root is None:
                scores.append(NEUTRAL_IMPORTANCE)
                continue
            try:
                path = resolve_source_path(root.path, photo.relative_path)
            except ValueError:
                scores.append(NEUTRAL_IMPORTANCE)
                continue
            if not path.is_file():
                scores.append(NEUTRAL_IMPORTANCE)
                continue
            scores.append(self.for_photo(photo, path))
        return scores

    def for_photo(self, photo: PhotoAsset, path: Path) -> float:
        """Return the importance of one photo file.

        The photo digest is used as the cache key when available. Otherwise a
        fast full-image fingerprint is computed and used, which keeps the cache
        correct for inventory rows that have not been digested yet.
        """
        if not self.enabled:
            return NEUTRAL_IMPORTANCE

        image = None
        cache_key = photo.digest
        if cache_key is None:
            image = self._open_image(path)
            if image is None:
                return NEUTRAL_IMPORTANCE
            cache_key = compute_image_fingerprint(image)

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        if image is None:
            image = self._open_image(path)
            if image is None:
                return NEUTRAL_IMPORTANCE

        try:
            detections = self._detector.detect(image)
        except Exception:
            # Importance is an optional enhancement. A detector failure must
            # never block a layout or a render, so fall back to neutral.
            return NEUTRAL_IMPORTANCE

        score = sum(
            detection.confidence
            for detection in detections
            if detection.class_name in IMPORTANT_CLASSES
        )
        value = NEUTRAL_IMPORTANCE + min(score, self._cap) * self._image_score_factor
        self._cache[cache_key] = value
        return value

    @staticmethod
    def _open_image(path: Path) -> Image.Image | None:
        """Open an image as RGB, returning ``None`` when it cannot be read."""
        try:
            with Image.open(path) as image:
                return image.convert("RGB")
        except OSError:
            return None
