from PIL import Image

from .ObjectDetector import Detection


class SmartCrop:
    """
    Object-aware crop.
    """

    PADDING_FACTOR = 0.15

    def crop(
        self,
        image: Image.Image,
        target_width: int,
        target_height: int,
        detections: list[Detection] | None = None,
    ) -> Image.Image:

        img_width, img_height = image.size

        target_ratio = target_width / target_height
        image_ratio = img_width / img_height

        if detections:
            x1 = min(d.bbox[0] for d in detections)
            y1 = min(d.bbox[1] for d in detections)
            x2 = max(d.bbox[2] for d in detections)
            y2 = max(d.bbox[3] for d in detections)

            pad_x = (x2 - x1) * self.PADDING_FACTOR
            pad_y = (y2 - y1) * self.PADDING_FACTOR

            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)

            x2 = min(img_width, x2 + pad_x)
            y2 = min(img_height, y2 + pad_y)

            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2

        else:
            center_x = img_width / 2
            center_y = img_height / 2

        if image_ratio > target_ratio:
            crop_width = img_height * target_ratio

            left = max(
                0,
                min(
                    img_width - crop_width,
                    center_x - crop_width / 2,
                ),
            )

            cropped = image.crop(
                (
                    left,
                    0,
                    left + crop_width,
                    img_height,
                )
            )

        else:
            crop_height = img_width / target_ratio

            top = max(
                0,
                min(
                    img_height - crop_height,
                    center_y - crop_height / 2,
                ),
            )

            cropped = image.crop(
                (
                    0,
                    top,
                    img_width,
                    top + crop_height,
                )
            )

        return cropped.resize(
            (target_width, target_height),
            Image.Resampling.LANCZOS,
        )
