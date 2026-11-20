"""Slot-aware rendering adapter over the existing collage renderer.

Given a validated :class:`LayoutTemplate` and per-slot photo assignments, this
module renders a page by cropping each assigned photo into its slot rectangle.
It reuses the existing ``SmartCrop`` and Pillow operations so visual behavior
stays consistent with the legacy renderer while decoupling layouts from photos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from photo_composition_designer.core.helpers import mm_to_px
from photo_composition_designer.core.settings import Settings
from photo_composition_designer.layouts.loader import LayoutTemplate
from photo_composition_designer.render.object_detector import ObjectDetector
from photo_composition_designer.render.smart_crop import SmartCrop

#: Normalized tolerance for neighbour detection. The old renderer compared
#: rounded YAML coordinates with ``1e-9``, which fails for values such as
#: ``0.133333`` versus ``0.133334``. A tolerance scaled to render resolution
#: treats sub-pixel drift as a true touch, so the spacing gutter is inserted.
_NEIGHBOUR_TOLERANCE = 1e-4


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
        spacing = mm_to_px(
            self._settings.layout.spacing.value,
            self._settings.size.dpi.value,
        )
        rounded_corners = self._settings.layout.useRoundedCorners.value

        for slot in layout.slots:
            x0 = int(round(slot.x * page_width))
            y0 = int(round(slot.y * page_height))
            x1 = int(round((slot.x + slot.width) * page_width))
            y1 = int(round((slot.y + slot.height) * page_height))
            # Compare edges in normalized space with a tolerance that absorbs
            # sub-pixel drift from rounded YAML coordinates (e.g. 0.133333).
            # The old 1e-9 check treated almost every row as non-touching and
            # the spacing gutter collapsed to zero.
            tol = _NEIGHBOUR_TOLERANCE
            neighbors = {
                "left": any(
                    abs(other.x + other.width - slot.x) < tol
                    and min(other.y + other.height, slot.y + slot.height) > max(other.y, slot.y)
                    for other in layout.slots
                    if other.key != slot.key
                ),
                "right": any(
                    abs(slot.x + slot.width - other.x) < tol
                    and min(other.y + other.height, slot.y + slot.height) > max(other.y, slot.y)
                    for other in layout.slots
                    if other.key != slot.key
                ),
                "top": any(
                    abs(other.y + other.height - slot.y) < tol
                    and min(other.x + other.width, slot.x + slot.width) > max(other.x, slot.x)
                    for other in layout.slots
                    if other.key != slot.key
                ),
                "bottom": any(
                    abs(slot.y + slot.height - other.y) < tol
                    and min(other.x + other.width, slot.x + slot.width) > max(other.x, slot.x)
                    for other in layout.slots
                    if other.key != slot.key
                ),
            }
            before = spacing // 2
            after = spacing - before
            if neighbors["left"]:
                x0 += after
            if neighbors["right"]:
                x1 -= before
            if neighbors["top"]:
                y0 += after
            if neighbors["bottom"]:
                y1 -= before
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

            crop_box = self._smart_crop.crop_box(
                image=image,
                target_width=slot_width,
                target_height=slot_height,
                detections=detections,
            )
            cropped = self._apply_crop_overrides(
                image,
                crop_box,
                assignment,
                target_width=slot_width,
                target_height=slot_height,
            )
            if rounded_corners and spacing > 0:
                mask = Image.new("L", cropped.size, 0)
                radius = min(spacing, cropped.width // 2, cropped.height // 2)
                ImageDraw.Draw(mask).rounded_rectangle(
                    (0, 0, cropped.width - 1, cropped.height - 1),
                    radius=radius,
                    fill=255,
                )
                page.paste(cropped, (x0, y0), mask)
            else:
                page.paste(cropped, (x0, y0))

        return page

    @staticmethod
    def _apply_crop_overrides(
        image: Image.Image,
        crop_box: tuple[int, int, int, int],
        assignment: SlotPhoto,
        *,
        target_width: int,
        target_height: int,
    ) -> Image.Image:
        """Apply per-assignment zoom and focal-point overrides to a cropped image.

        A focal point of ``(0.5, 0.5)`` preserves the smart crop. Other values
        pan the crop window within the source image, including areas discarded
        by the smart crop. Values are clamped so the crop stays inside the image.
        """
        zoom = assignment.crop_zoom if assignment.crop_zoom and assignment.crop_zoom > 0 else 1.0
        focus_x = min(1.0, max(0.0, assignment.crop_focus_x))
        focus_y = min(1.0, max(0.0, assignment.crop_focus_y))
        base_left, base_top, base_right, base_bottom = crop_box
        base_width = base_right - base_left
        base_height = base_bottom - base_top
        crop_width = max(1, min(image.width, int(round(base_width / zoom))))
        crop_height = max(1, min(image.height, int(round(base_height / zoom))))
        centered_left = base_left + (base_width - crop_width) / 2
        centered_top = base_top + (base_height - crop_height) / 2

        def position(start: float, base_start: float, max_start: int, focus: float) -> int:
            if focus < 0.5:
                value = start + (base_start - start) * (focus * 2)
            else:
                value = base_start + (max_start - base_start) * ((focus - 0.5) * 2)
            return int(round(value))

        left = position(0, centered_left, image.width - crop_width, focus_x)
        top = position(0, centered_top, image.height - crop_height, focus_y)
        cropped = image.crop((left, top, left + crop_width, top + crop_height))
        return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
