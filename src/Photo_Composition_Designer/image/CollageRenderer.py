import random
from logging import Logger

from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.image.SmartCrop import SmartCrop

IMAGE_SCORE_FACTOR = 0.35

from dataclasses import dataclass


@dataclass
class LayoutNode:
    pass


@dataclass
class ImageNode(LayoutNode):
    image: Image.Image


@dataclass
class SplitNode(LayoutNode):
    direction: str
    children: list
    weights: list[float]


class CollageRenderer:
    """
    Renders a collage of images with various layout options,
    optionally using object recognition for smart cropping.
    """

    def __init__(
        self,
        width=900,
        height=600,
        spacing=10,
        color=(0, 0, 0),
        use_object_recognition=False,
    ):
        self.color = color
        self.width: int = width
        self.height: int = height
        self.spacing: int = spacing
        self.yolo_session = None  # Will load this lazily
        self.use_image_recognition = use_object_recognition
        self.detector = ObjectDetector() if use_object_recognition else None
        self.cropper = SmartCrop()

        # Initialize logging system
        initialize_logging()
        self.logger: Logger = get_logger("base")
        self.logger.info("CollageRenderer initialized.")

    def _calculateLayoutWeight(self, image):
        """
        Gewicht für die Layout-Optimierung.

        Berücksichtigt:
        - Seitenverhältnis
        - Bildinhalt (Personen/Tiere/etc.)

        Berücksichtigt NICHT:
        - Auflösung
        - Dateigröße
        """

        aspect_ratio = image.width / image.height

        score = self._calculateImageScore(image)

        score_factor = 1.0 + (score / 100.0) * IMAGE_SCORE_FACTOR

        return aspect_ratio * score_factor

    def _generateLayout(
        self,
        images,
        target_width,
        target_height,
    ):
        """
        Rekursive Layout-Erzeugung.

        Liefert einen Layout-Baum zurück.
        """

        if len(images) == 1:
            return ImageNode(images[0])

        if len(images) == 2:
            return self._generateTwoImageLayout(
                images,
                target_width,
                target_height,
            )

        canvas_ratio = target_width / target_height

        weighted_images = sorted(
            images,
            key=self._calculateLayoutWeight,
            reverse=True,
        )

        split_index = self._findBestSplit(weighted_images)

        group_a = weighted_images[:split_index]
        group_b = weighted_images[split_index:]

        sum_a = sum(self._calculateLayoutWeight(img) for img in group_a)

        sum_b = sum(self._calculateLayoutWeight(img) for img in group_b)

        if canvas_ratio >= 1.0:
            direction = "vertical"
        else:
            direction = "horizontal"

        child_a = self._generateLayout(
            group_a,
            target_width,
            target_height,
        )

        child_b = self._generateLayout(
            group_b,
            target_width,
            target_height,
        )

        return SplitNode(
            direction=direction,
            children=[child_a, child_b],
            weights=[sum_a, sum_b],
        )

    def _findBestSplit(self, images):

        weights = [self._calculateLayoutWeight(img) for img in images]

        total = sum(weights)

        current = 0

        best_index = 1
        best_error = float("inf")

        for i in range(1, len(weights)):
            current += weights[i - 1]

            error = abs(current - (total - current))

            if error < best_error:
                best_error = error
                best_index = i

        return best_index

    def _generateTwoImageLayout(
        self,
        images,
        width,
        height,
    ):

        if width >= height:
            return SplitNode(
                direction="vertical",
                children=[
                    ImageNode(images[0]),
                    ImageNode(images[1]),
                ],
                weights=[
                    self._calculateLayoutWeight(images[0]),
                    self._calculateLayoutWeight(images[1]),
                ],
            )

        return SplitNode(
            direction="horizontal",
            children=[
                ImageNode(images[0]),
                ImageNode(images[1]),
            ],
            weights=[
                self._calculateLayoutWeight(images[0]),
                self._calculateLayoutWeight(images[1]),
            ],
        )

    def _renderLayout(
        self,
        collage,
        node,
        x,
        y,
        width,
        height,
    ):
        if isinstance(node, ImageNode):
            img = self._cropAndResize(
                node.image,
                width,
                height,
            )

            collage.paste(
                img,
                (int(x), int(y)),
            )

            return
        weight_sum = sum(node.weights)

        w1 = node.weights[0] / weight_sum
        w2 = node.weights[1] / weight_sum

        if node.direction == "vertical":
            split = int(width * w1)

            self._renderLayout(
                collage,
                node.children[0],
                x,
                y,
                split - self.spacing // 2,
                height,
            )

            self._renderLayout(
                collage,
                node.children[1],
                x + split + self.spacing // 2,
                y,
                width - split - self.spacing // 2,
                height,
            )

            return

        split = int(height * w1)

        self._renderLayout(
            collage,
            node.children[0],
            x,
            y,
            width,
            split - self.spacing // 2,
        )

        self._renderLayout(
            collage,
            node.children[1],
            x,
            y + split + self.spacing // 2,
            width,
            height - split - self.spacing // 2,
        )

    def generate(self, images: list[Image.Image]) -> Image.Image:
        """
        Arranges images dynamically based on canvas ratio and content,
        generating a complete collage image.

        Args:
            images: A list of PIL Image objects to be arranged in the collage.

        Returns:
            A PIL Image object representing the generated collage.
            Returns an empty canvas if no valid images are provided or
            if an unrecoverable error occurs.
        """

        self.logger.info("Starting collage generation.")

        if not images:
            self.logger.warning(
                "No images provided for collage generation. Returning empty canvas."
            )
            return Image.new("RGB", (self.width, self.height), self.color)

        # Filter out non-PIL Image objects and corrupted images
        images = self._sanitize(images)
        images = self._filter_valid(images)

        if not images:
            self.logger.error(
                "All provided images were invalid or corrupted after sanitization. "
                "Returning empty canvas."
            )
            return Image.new("RGB", (self.width, self.height), self.color)
        self.logger.info(f"Starting collage generation for {len(images)} images.")

        layout = self._generateLayout(
            images,
            self.width,
            self.height,
        )

        collage = Image.new(
            "RGB",
            (self.width, self.height),
            self.color,
        )

        self._renderLayout(
            collage,
            layout,
            0,
            0,
            self.width,
            self.height,
        )

        return collage

    def _sanitize(self, images: list[Image.Image]) -> list[Image.Image]:
        """
        Filters out non-PIL Image objects from the input list.

        Args:
            images: A list of potential PIL Image objects.

        Returns:
            A list containing only valid PIL Image objects.
        """
        valid_images = [img for img in images if isinstance(img, Image.Image)]
        if len(valid_images) < len(images):
            self.logger.warning(
                f"Removed {len(images) - len(valid_images)} non-Image objects from input."
            )
        return valid_images

    def _filter_valid(self, images: list[Image.Image]) -> list[Image.Image]:
        """
        Filters out images that cause errors during basic PIL operations (e.g., corrupted files).

        Args:
            images: A list of PIL Image objects.

        Returns:
            A list containing only valid and readable PIL Image objects.
        """
        valid = []
        for img in images:
            try:
                # Attempt a simple operation to check image validity (e.g., access a pixel)
                img.getpixel((0, 0))
                valid.append(img)
            except Exception as e:
                self.logger.warning(f"Invalid or corrupted image detected and removed: {e}")
                continue
        return valid


    def _cropAndResize(self, image, target_width, target_height):
        """
        Crops an image proportionally and then scales it to the desired size.
        Attempts to retain recognized objects in the image.
        """
        detections = None
        if self.detector:
            self.logger.info("Object detection enabled. Detecting objects for smart crop.")
            detections = self.detector.detect(image)
            self.logger.info(f"Detected {len(detections)} objects.")
        else:
            self.logger.info("Object detection disabled. Performing standard crop.")

        cropped_image, _ = self.cropper.crop(
            image=image,
            target_width=target_width,
            target_height=target_height,
            detections=detections,
        )
        return cropped_image

    def _calculateImageScore(
        self,
        image,
    ):
        """
        Calculates a score for an image based on detected objects,
        prioritizing certain object types.
        """
        if not self.detector:
            self.logger.info("Object detector not initialized, returning score 0.")
            return 0

        score = 0
        detections = self.detector.detect(image)
        self.logger.info(f"Calculating score for image with {len(detections)} detections.")

        for d in detections:
            if d.class_name == "person":
                score += 5
            elif d.class_name in ("dog", "cat"):
                score += 4
            elif d.class_name == "bicycle":
                score += 3
            elif d.class_name in ("car", "motorcycle"):
                score += 2
            self.logger.info(
                f"Object '{d.class_name}' (confidence: {d.confidence:.2f}) "
                f"added to score. Current score: {score}"
            )
        return score
