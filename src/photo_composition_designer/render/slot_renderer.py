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
            cropped = self._apply_crop_overrides(cropped, assignment)
            page.paste(cropped, (x0, y0))

        return page

    @staticmethod
    def _apply_crop_overrides(image: Image.Image, assignment: SlotPhoto) -> Image.Image:
        """Apply per-assignment zoom and focal-point overrides to a cropped image.

        ``crop_zoom`` of 1.0 and a focal point of ``(0.5, 0.5)`` leave the
        smart-cropped image unchanged. Values are clamped so the crop window
        always stays inside the image.
        """
        zoom = assignment.crop_zoom if assignment.crop_zoom and assignment.crop_zoom > 0 else 1.0
        focus_x = min(1.0, max(0.0, assignment.crop_focus_x))
        focus_y = min(1.0, max(0.0, assignment.crop_focus_y))
        if abs(zoom - 1.0) < 1e-6 and abs(focus_x - 0.5) < 1e-6 and abs(focus_y - 0.5) < 1e-6:
            return image

        width, height = image.size
        crop_width = max(1, min(width, int(round(width / zoom))))
        crop_height = max(1, min(height, int(round(height / zoom))))
        left = int(round(focus_x * width - crop_width / 2))
        top = int(round(focus_y * height - crop_height / 2))
        left = max(0, min(left, width - crop_width))
        top = max(0, min(top, height - crop_height))
        cropped = image.crop((left, top, left + crop_width, top + crop_height))
        return cropped.resize((width, height), Image.Resampling.LANCZOS)
