from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .ObjectDetector import Detection


@dataclass(frozen=True)
class CropRegion:
    """
    Represents a rectangular region.
    """

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2


class SmartCrop:
    """
    Object-aware image crop optimized for photo calendar layouts.

    The crop is centered around a weighted visual anchor point
    derived from detected objects.

    Important objects such as people and animals use an anchor
    shifted upward to protect heads and faces during vertical crops.
    """

    PADDING_FACTOR = 0.15

    DEFAULT_OBJECT_PRIORITIES = {
        "person": 5,
        "dog": 4,
        "cat": 4,
        "horse": 4,
        "bird": 3,
        "bicycle": 3,
        "car": 2,
        "motorcycle": 2,
        "bus": 2,
    }

    #
    # Visual anchor positions.
    #
    # 0.5 = geometric center
    # 0.35 = upper body / face area
    #
    ANCHOR_Y_FACTORS = {
        "person": 0.35,
        "dog": 0.35,
        "cat": 0.35,
        "horse": 0.35,
        "bird": 0.35,
    }

    def __init__(self, object_priorities: dict[str, int] | None = None):
        """
        Initialize SmartCrop.

        Args:
            object_priorities:
                Optional mapping of class name to priority.
        """
        self.object_priorities = (
            object_priorities if object_priorities is not None else self.DEFAULT_OBJECT_PRIORITIES
        )

    def _calculate_effective_region(
        self,
        detections: list[Detection],
        img_width: int,
        img_height: int,
    ) -> CropRegion:
        """
        Calculates a padded bounding region containing all detections.
        """

        min_x = min(d.bbox[0] for d in detections)
        min_y = min(d.bbox[1] for d in detections)
        max_x = max(d.bbox[2] for d in detections)
        max_y = max(d.bbox[3] for d in detections)

        pad_x = (max_x - min_x) * self.PADDING_FACTOR
        pad_y = (max_y - min_y) * self.PADDING_FACTOR

        return CropRegion(
            left=max(0, min_x - pad_x),
            top=max(0, min_y - pad_y),
            right=min(img_width, max_x + pad_x),
            bottom=min(img_height, max_y + pad_y),
        )

    def _get_detection_anchor(
        self,
        detection: Detection,
    ) -> tuple[float, float]:
        """
        Returns the visual anchor point for a detection.

        Humans and animals use an anchor shifted upwards
        to preserve heads and faces.
        """

        x1, y1, x2, y2 = detection.bbox

        anchor_factor = self.ANCHOR_Y_FACTORS.get(
            detection.class_name,
            0.5,
        )

        anchor_x = (x1 + x2) / 2
        anchor_y = y1 + (y2 - y1) * anchor_factor

        return anchor_x, anchor_y

    def _calculate_detection_weight(
        self,
        detection: Detection,
    ) -> float:
        """
        Calculate detection weight.

        Formula:

            priority * confidence * sqrt(area)

        This gives more influence to:
        - important classes
        - confident detections
        - larger objects

        while preventing very large objects from completely dominating.
        """

        x1, y1, x2, y2 = detection.bbox

        area = max(1.0, (x2 - x1) * (y2 - y1))

        priority = self.object_priorities.get(
            detection.class_name,
            1,
        )

        return priority * (detection.confidence or 0.0) * math.sqrt(area)

    def _calculate_weighted_anchor(
        self,
        detections: list[Detection],
        fallback_region: CropRegion,
    ) -> tuple[float, float]:
        """
        Calculate weighted anchor point from detections.
        """

        weighted_x = 0.0
        weighted_y = 0.0
        total_weight = 0.0

        for detection in detections:
            anchor_x, anchor_y = self._get_detection_anchor(detection)

            weight = self._calculate_detection_weight(detection)

            weighted_x += anchor_x * weight
            weighted_y += anchor_y * weight
            total_weight += weight

        if total_weight <= 0:
            return (
                fallback_region.center_x,
                fallback_region.center_y,
            )

        return (
            weighted_x / total_weight,
            weighted_y / total_weight,
        )

    def _calculate_crop_box(
        self,
        img_width: int,
        img_height: int,
        target_ratio: float,
        center_x: float,
        center_y: float,
        detections: list[Detection] | None,
    ) -> tuple[int, int, int, int]:
        """
        Calculates crop coordinates around a visual anchor point.
        """

        image_ratio = img_width / img_height

        #
        # Horizontal crop
        #
        if image_ratio > target_ratio:
            crop_width = img_height * target_ratio
            crop_height = img_height

            left = max(
                0,
                min(
                    img_width - crop_width,
                    center_x - crop_width / 2,
                ),
            )

            top = 0

        #
        # Vertical crop
        #
        else:
            crop_width = img_width
            crop_height = img_width / target_ratio

            top = max(
                0,
                min(
                    img_height - crop_height,
                    center_y - crop_height / 2,
                ),
            )

            #
            # Head protection:
            #
            # Prevent the crop from cutting off
            # the upper part of important objects.
            #
            if detections:
                important_top = min(
                    d.bbox[1]
                    for d in detections
                    if self.object_priorities.get(
                        d.class_name,
                        1,
                    )
                )

                top = min(top, important_top)

                top = max(
                    0,
                    min(
                        top,
                        img_height - crop_height,
                    ),
                )

            left = 0

        right = left + crop_width
        bottom = top + crop_height

        return (
            int(round(left)),
            int(round(top)),
            int(round(right)),
            int(round(bottom)),
        )

    def _get_crop_coordinates(
        self,
        img_width: int,
        img_height: int,
        target_ratio: float,
        detections: list[Detection] | None = None,
    ) -> tuple[int, int, int, int]:
        """
        Determine crop coordinates.
        """

        if not detections:
            center_x = img_width / 2
            center_y = img_height / 2

            return self._calculate_crop_box(
                img_width,
                img_height,
                target_ratio,
                center_x,
                center_y,
                None,
            )

        effective_region = self._calculate_effective_region(
            detections,
            img_width,
            img_height,
        )

        center_x, center_y = self._calculate_weighted_anchor(
            detections,
            effective_region,
        )

        return self._calculate_crop_box(
            img_width,
            img_height,
            target_ratio,
            center_x,
            center_y,
            detections,
        )

    def crop(
        self,
        image: Image.Image,
        target_width: int,
        target_height: int,
        detections: list[Detection] | None = None,
    ) -> tuple[Image.Image, tuple[int, int, int, int]]:
        """
        Perform smart crop and resize.
        """

        img_width, img_height = image.size

        crop_box = self._get_crop_coordinates(
            img_width=img_width,
            img_height=img_height,
            target_ratio=target_width / target_height,
            detections=detections,
        )

        cropped = image.crop(crop_box)

        resized = cropped.resize(
            (target_width, target_height),
            Image.Resampling.LANCZOS,
        )

        return resized, crop_box

    def visualize_crop(
        self,
        original_image: Image.Image,
        detections: list[Detection],
        crop_box: tuple[int, int, int, int],
        output_max_dim: int = 1080,
    ) -> Image.Image:
        """
        Visualize detections and crop box.
        """

        image = original_image.copy().convert("RGB")

        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype(
                "arial.ttf",
                20,
            )
        except OSError:
            font = ImageFont.load_default()

        for detection in detections:
            x1, y1, x2, y2 = detection.bbox

            draw.rectangle(
                [x1, y1, x2, y2],
                outline="red",
                width=1,
            )

            anchor_x, anchor_y = self._get_detection_anchor(detection)

            draw.ellipse(
                (
                    anchor_x - 4,
                    anchor_y - 4,
                    anchor_x + 4,
                    anchor_y + 4,
                ),
                fill="yellow",
            )

            label = f"{detection.class_name} ({detection.confidence:.2f})"

            draw.text(
                (x1, max(0, y1 - 20)),
                label,
                fill="red",
                font=font,
            )

        draw.rectangle(
            crop_box,
            outline="blue",
            width=3,
        )

        width, height = image.size

        if max(width, height) > output_max_dim:
            scale = output_max_dim / max(
                width,
                height,
            )

            image = image.resize(
                (
                    int(width * scale),
                    int(height * scale),
                ),
                Image.Resampling.LANCZOS,
            )

        return image
