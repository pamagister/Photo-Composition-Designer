import math
import random
from logging import Logger
from operator import itemgetter

from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.image.SmartCrop import SmartCrop

IMAGE_SCORE_FACTOR = 0.8

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

def linear_partition_table(seq, k):
    n = len(seq)
    table = [[0] * k for x in range(n)]
    solution = [[0] * (k - 1) for x in range(n - 1)]
    for i in range(n):
        table[i][0] = seq[i] + (table[i - 1][0] if i else 0)
    for j in range(k):
        table[0][j] = seq[0]
    for i in range(1, n):
        for j in range(1, k):
            table[i][j], solution[i - 1][j - 1] = min(
                ((max(table[x][j - 1], table[i][0] - table[x][0]), x) for x in range(i)),
                key=itemgetter(0))
    return (table, solution)

def linear_partition(seq, k, data_list=None, do_rotate=False):
    if k <= 0:
        return []
    n = len(seq) - 1
    if k > n:
        return map(lambda x: [x], seq)
    _, solution = linear_partition_table(seq, k)
    k, ans = k - 2, []
    if data_list == None or len(data_list) != len(seq):
        while k >= 0:
            row = [[seq[i] for i in range(solution[n - 1][k] + 1, n + 1)]]
            if do_rotate:
                ans += row
            else:
                ans = row + ans
            n, k = solution[n - 1][k], k - 1
        row = [[seq[i] for i in range(0, n + 1)]]
        if do_rotate:
            ans += row
        else:
            ans = row + ans
    else:
        while k >= 0:
            row = [[data_list[i] for i in range(solution[n - 1][k] + 1, n + 1)]]
            if do_rotate:
                ans += row
            else:
                ans = row + ans
            n, k = solution[n - 1][k], k - 1
        row = [[data_list[i] for i in range(0, n + 1)]]
        if do_rotate:
            ans += row
        else:
            ans = row + ans
    return ans


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

    def _generateLayout(self, images, target_width, target_height):
        """
        Erzeugt ein stabil balanciertes Layout basierend auf echter Partitionierung
        statt greedy rekursiven Splits.
        """

        n = len(images)

        if n == 1:
            return ImageNode(images[0])

        # Gewichte berechnen (wie vorher)
        weights = [self._calculateLayoutWeight(img) for img in images]

        # Ziel: Anzahl "Zeilen" heuristisch bestimmen
        canvas_ratio = target_width / target_height
        num_rows = max(1, min(n, int(round(math.sqrt(n / canvas_ratio)))))

        # Partitionierung (wie im Referenzalgorithmus)
        rows = linear_partition(weights, num_rows, images)

        # Jede Zeile wird ein SplitNode (horizontal = Bilder nebeneinander)
        row_nodes = []
        row_weights = []

        for row in rows:
            if len(row) == 1:
                row_nodes.append(ImageNode(row[0]))
                row_weights.append(self._calculateLayoutWeight(row[0]))
            else:
                w = [self._calculateLayoutWeight(img) for img in row]
                row_nodes.append(SplitNode(
                    direction="vertical",
                    children=[ImageNode(img) for img in row],
                    weights=w
                ))
                row_weights.append(sum(w))

        # Falls nur eine Zeile → direkt zurück
        if len(row_nodes) == 1:
            return row_nodes[0]

        return SplitNode(
            direction="horizontal",
            children=row_nodes,
            weights=row_weights
        )

    def _renderLayout(self, collage, node, x, y, width, height):
        # Leaf
        if isinstance(node, ImageNode):
            img = self._cropAndResize(node.image, width, height)
            collage.paste(img, (int(x), int(y)))
            return

        if not node.children:
            return

        weight_sum = sum(node.weights) if node.weights else len(node.children)

        # --- VERTICAL SPLIT (nebeneinander) ---
        if node.direction == "vertical":
            current_x = x

            for i, child in enumerate(node.children):
                w = node.weights[i] if node.weights else 1
                w_ratio = w / weight_sum

                cw = int(width * w_ratio)

                # letzter block bekommt Rest (verhindert Drift)
                if i == len(node.children) - 1:
                    cw = x + width - current_x

                self._renderLayout(
                    collage,
                    child,
                    current_x,
                    y,
                    cw - self.spacing // 2,
                    height
                )

                current_x += cw + self.spacing

            return

        # --- HORIZONTAL SPLIT (untereinander) ---
        current_y = y

        for i, child in enumerate(node.children):
            h = node.weights[i] if node.weights else 1
            h_ratio = h / weight_sum

            ch = int(height * h_ratio)

            if i == len(node.children) - 1:
                ch = y + height - current_y

            self._renderLayout(
                collage,
                child,
                x,
                current_y,
                width,
                ch - self.spacing // 2
            )

            current_y += ch + self.spacing

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
