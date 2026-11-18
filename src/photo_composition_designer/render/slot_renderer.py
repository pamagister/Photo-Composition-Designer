"""Slot-aware rendering adapter over the existing collage renderer.

Given a validated :class:`LayoutTemplate` and per-slot photo assignments, this
module renders a page by cropping each assigned photo into its slot rectangle.
It reuses the existing ``SmartCrop`` and Pillow operations so visual behavior
stays consistent with the legacy renderer while decoupling layouts from photos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.settings import Settings
from photo_composition_designer.layouts.loader import LayoutTemplate
from photo_composition_designer.render.object_detector import ObjectDetector
from photo_composition_designer.render.smart_crop import SmartCrop


@dataclass(frozen=True)
class SlotPhoto:
    """A photo assigned to a slot with optional crop overrides."""

    photo_path: Path
    crop_zoom: float = 1.0
    crop_focus_x: float = 0.5
    crop_focus_y: float = 0.5


def _resolve_crop_mode(mode: str) -> Image.Resampling:
    """Map a crop mode to a Pillow resampling filter for resizing."""
    return Image.Resampling.LANCZOS


class SlotAwareRenderer:
    """Render a page from a layout template and per-slot photo assignments."""

    def __init__(
        self,
        settings: Settings,
        *,
        object_detector: ObjectDetector | None = None,
    ) -> None:
        self._settings = settings
        self._object_detector = object_detector
        self._smart_crop = SmartCrop()

    def render(
        self,
        layout: LayoutTemplate,
        assignments: dict[str, SlotPhoto | None],
        *,
        page_width: int,
        page_height: int,
        background_color: tuple[int, int, int],
    ) -> Image.Image:
        """Render one page image from a layout and slot assignments."""
        page = Image.new("RGB", (page_width, page_height), background_color)

        for slot in layout.slots:
            x0 = int(round(slot.x * page_width))
            y0 = int(round(slot.y * page_height))
            x1 = int(round((slot.x + slot.width) * page_width))
            y1 = int(round((slot.y + slot.height) * page_height))
            slot_width = max(1, x1 - x0)
            slot_height = max(1, y1 - y0)

            assignment = assignments.get(slot.key)
            if assignment is None:
                continue

            with Image.open(assignment.photo_path) as source:
                image = source.convert("RGB")

            detections = None
            if self._object_detector is not None:
                detections = self._object_detector.detect(image)

            cropped, _box = self._smart_crop.crop(
                image=image,
                target_width=slot_width,
                target_height=slot_height,
                detections=detections,
            )
            page.paste(cropped, (x0, y0))

        return page
