from PIL import Image, ImageDraw, ImageFont

from .ObjectDetector import Detection


class SmartCrop:
    """
    Object-aware crop.
    """

    PADDING_FACTOR = 0.15
    # Define default object priorities. Higher value means higher priority.
    # This can be customized when instantiating SmartCrop or passed to the crop method.
    DEFAULT_OBJECT_PRIORITIES = {
        "person": 5,
        "dog": 4,
        "cat": 4,
        "bicycle": 3,
        "car": 2,
        "motorcycle": 2,
        "bus": 2,
        # Add more objects and their priorities as needed
    }

    def __init__(self, object_priorities: dict = None):
        """
        Initializes the SmartCrop instance with optional object priorities.

        Args:
            object_priorities: A dictionary mapping object class names to their priority scores.
                               If None, DEFAULT_OBJECT_PRIORITIES will be used.
        """
        self.object_priorities = (
            object_priorities if object_priorities is not None else self.DEFAULT_OBJECT_PRIORITIES
        )

    def _get_crop_coordinates(
        self,
        img_width: int,
        img_height: int,
        target_ratio: float,
        detections: list[Detection] | None = None,
    ) -> tuple[int, int, int, int]:
        """
        Calculates the optimal crop coordinates based on detections and target aspect ratio.

        Args:
            img_width: The width of the original image.
            img_height: The height of the original image.
            target_ratio: The aspect ratio (width / height) of the target crop.
            detections: A list of detected objects (Detection objects).

        Returns:
            A tuple containing the (left, top, right, bottom) coordinates of the crop box.
        """
        center_x, center_y = img_width / 2, img_height / 2

        # Initialize effective bounding box to full image dimensions
        effective_x1, effective_y1, effective_x2, effective_y2 = 0, 0, img_width, img_height

        if detections:
            # Calculate a combined bounding box for all detections
            min_x = min(d.bbox[0] for d in detections)
            min_y = min(d.bbox[1] for d in detections)
            max_x = max(d.bbox[2] for d in detections)
            max_y = max(d.bbox[3] for d in detections)

            # Apply padding to the combined bounding box
            pad_x = (max_x - min_x) * self.PADDING_FACTOR
            pad_y = (max_y - min_y) * self.PADDING_FACTOR

            effective_x1 = max(0, min_x - pad_x)
            effective_y1 = max(0, min_y - pad_y)
            effective_x2 = min(img_width, max_x + pad_x)
            effective_y2 = min(img_height, max_y + pad_y)

            # Calculate weighted center based on priorities
            weighted_sum_x = 0
            weighted_sum_y = 0
            total_weight = 0
            for d in detections:
                # Get priority for the object class, default to 1 if not specified
                weight = self.object_priorities.get(d.class_name, 1)
                obj_center_x = (d.bbox[0] + d.bbox[2]) / 2
                obj_center_y = (d.bbox[1] + d.bbox[3]) / 2
                weighted_sum_x += obj_center_x * weight
                weighted_sum_y += obj_center_y * weight
                total_weight += weight

            if total_weight > 0:
                center_x = weighted_sum_x / total_weight
                center_y = weighted_sum_y / total_weight
            else:  # Fallback to geometric center of the combined effective box
                center_x = (effective_x1 + effective_x2) / 2
                center_y = (effective_y1 + effective_y2) / 2

        # Corrected fallback for center_y
        if not detections or total_weight == 0:
            center_x = (effective_x1 + effective_x2) / 2
            center_y = (effective_y1 + effective_y2) / 2

        image_ratio = img_width / img_height

        if image_ratio > target_ratio:  # Original image is wider than target, crop width
            crop_width = img_height * target_ratio
            crop_height = img_height

            # Adjust crop_width if it exceeds image width
            if crop_width > img_width:
                crop_width = img_width
                crop_height = (
                    img_width / target_ratio
                )  # Recalculate height to maintain target ratio

            left = max(
                0,
                min(
                    img_width - crop_width,
                    center_x - crop_width / 2,
                ),
            )
            top = (img_height - crop_height) / 2  # Center vertically if cropping horizontally
            right = left + crop_width
            bottom = top + crop_height

        else:  # Original image is taller than target, crop height
            crop_height = img_width / target_ratio
            crop_width = img_width

            # Adjust crop_height if it exceeds image height
            if crop_height > img_height:
                crop_height = img_height
                crop_width = img_height * target_ratio  # Recalculate width to maintain target ratio

            top = max(
                0,
                min(
                    img_height - crop_height,
                    center_y - crop_height / 2,
                ),
            )
            left = (img_width - crop_width) / 2  # Center horizontally if cropping vertically
            right = left + crop_width
            bottom = top + crop_height

        return int(left), int(top), int(right), int(bottom)

    def crop(
        self,
        image: Image.Image,
        target_width: int,
        target_height: int,
        detections: list[Detection] | None = None,
    ) -> tuple[Image.Image, tuple[int, int, int, int]]:  # Return cropped image and crop box
        """
        Performs an object-aware crop on the given image.

        Args:
            image: The input PIL Image.
            target_width: The desired width of the output image.
            target_height: The desired height of the output image.
            detections: A list of detected objects (Detection objects).

        Returns:
            A tuple containing:
            - The cropped and resized PIL Image.
            - The coordinates of the crop box (left, top, right, bottom)
              in the original image.
        """
        img_width, img_height = image.size
        target_ratio = target_width / target_height

        crop_box = self._get_crop_coordinates(img_width, img_height, target_ratio, detections)

        cropped_image = image.crop(crop_box)

        return (
            cropped_image.resize(
                (target_width, target_height),
                Image.Resampling.LANCZOS,
            ),
            crop_box,
        )

    def visualize_crop(
        self,
        original_image: Image.Image,
        detections: list[Detection],
        crop_box: tuple[int, int, int, int],
        output_max_dim: int = 1080,  # Normalize long edge to HD for visualization
    ) -> Image.Image:
        """
        Draws detected objects and the final crop box on a copy of the original image.
        The output image is normalized to a maximum dimension for consistent visualization.

        Args:
            original_image: The original PIL Image before cropping.
            detections: A list of detected objects (Detection objects).
            crop_box: The (left, top, right, bottom) coordinates of the crop box
                      in the original image.
            output_max_dim: The maximum dimension (width or height) for the output
                            visualized image.

        Returns:
            A new PIL Image with detections and crop box drawn.
        """
        draw_image = original_image.copy().convert("RGB")  # Ensure image is in RGB mode
        draw = ImageDraw.Draw(draw_image)

        # Load a font for labels
        try:
            # Try to load a common font, fallback to default
            font = ImageFont.truetype("arial.ttf", 20)
        except OSError:
            font = ImageFont.load_default()

        # Draw detected objects (thin boxes)
        for d in detections:
            x1, y1, x2, y2 = d.bbox
            draw.rectangle([x1, y1, x2, y2], outline="red", width=1)
            label = f"{d.class_name} ({d.confidence:.2f})"
            # Adjust text position to be above the box, or inside if too close to top edge
            text_y_pos = y1 - 20
            if text_y_pos < 0:
                text_y_pos = y1 + 5  # Draw inside if not enough space above
            draw.text((x1, text_y_pos), label, fill="red", font=font)

        # Draw final crop box (thick border)
        crop_x1, crop_y1, crop_x2, crop_y2 = crop_box
        draw.rectangle([crop_x1, crop_y1, crop_x2, crop_y2], outline="blue", width=3)

        # Normalize to HD (long edge) for visualization
        img_width, img_height = draw_image.size
        if max(img_width, img_height) > output_max_dim:
            if img_width > img_height:
                new_width = output_max_dim
                new_height = int(img_height * (new_width / img_width))
            else:
                new_height = output_max_dim
                new_width = int(img_width * (new_height / img_height))
            draw_image = draw_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        return draw_image
