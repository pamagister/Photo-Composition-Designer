import math
from collections import deque
from dataclasses import dataclass
from logging import Logger
from operator import itemgetter

from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image, ImageDraw

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.image.SmartCrop import SmartCrop

PATTERNS = [
    ["P", "L", "L", "P"],
    ["L", "P", "P", "L"],
    ["P", "L", "P"],
    ["L", "P", "L"],
    ["L", "P", "L", "P", "L"],
    ["P", "P", "L", "P", "P"],
]


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
                key=itemgetter(0),
            )
    return table, solution


def linear_partition(seq, k, data_list=None, do_rotate=False):
    if k <= 0:
        return []
    n = len(seq) - 1
    if k > n:
        return ([x] for x in seq)
    _, solution = linear_partition_table(seq, k)
    k, ans = k - 2, []
    if data_list is None or len(data_list) != len(seq):
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

    DEFAULT_IMAGE_SCORE_FACTOR = 0.6

    def __init__(
        self,
        width=900,
        height=600,
        spacing=10,
        color=(0, 0, 0),
        use_object_recognition=False,
        rounded_corners=False,
        image_score_factor: float = DEFAULT_IMAGE_SCORE_FACTOR,
        object_detector: ObjectDetector | None = None,  # Added object_detector parameter
    ):
        self.color = color
        self.width: int = width
        self.height: int = height
        self.spacing: int = spacing
        self.rounded_corners = rounded_corners
        self.image_score_factor = image_score_factor
        self.yolo_session = None  # Will load this lazily
        self.use_image_recognition = use_object_recognition
        self.detector = object_detector  # Use the passed object_detector
        self.cropper = SmartCrop()

        # Initialize logging system
        initialize_logging()
        self.logger: Logger = get_logger("base")
        self.logger.info("CollageRenderer initialized.")

    def _applyRoundedCorners(self, image):
        if not self.rounded_corners:
            return image

        radius = self.spacing

        mask = Image.new("L", image.size, 0)

        draw = ImageDraw.Draw(mask)

        draw.rounded_rectangle(
            (0, 0, image.width, image.height),
            radius=radius,
            fill=255,
        )

        image = image.convert("RGBA")
        image.putalpha(mask)

        return image

    def _flip_layout(self, node):
        if isinstance(node, ImageNode):
            return node

        flipped_children = [self._flip_layout(c) for c in node.children]

        return SplitNode(
            direction=("horizontal" if node.direction == "vertical" else "vertical"),
            children=flipped_children,
            weights=node.weights,
        )

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
        portrait_factor = 1 if image.width < image.height else 1

        score = self._calculateImageScore(image)

        score_factor = 1.0 + (score / 50.0) * self.image_score_factor * portrait_factor

        return score_factor * aspect_ratio

    def _generateTwoImageLayout(
        self,
        images,
        width,
        height,
    ):

        is_portrait_canvas = height > width

        direction = "horizontal" if is_portrait_canvas else "vertical"

        return SplitNode(
            direction=direction,
            children=[
                ImageNode(images[0]),
                ImageNode(images[1]),
            ],
            weights=[
                self._calculateLayoutWeight(images[0]),
                self._calculateLayoutWeight(images[1]),
            ],
        )

    def _chooseBestThreeLayout(self, images, w, h):
        ratios = [img.width / img.height for img in images]

        is_portrait = [r < 0.9 for r in ratios]
        p_count = sum(is_portrait)

        weights = [self._calculateLayoutWeight(img) for img in images]

        # --- FALL 1.1: PPP (alle hochkant) ---
        if p_count == 3:
            return SplitNode(
                direction="vertical",
                children=[
                    ImageNode(images[0]),
                    ImageNode(images[1]),
                    ImageNode(images[2]),
                ],
                weights=weights,
            )

        # --- FALL 1.2: LLL (alle quer) ---
        if p_count == 0:
            return SplitNode(
                direction="horizontal",
                children=[
                    ImageNode(images[0]),
                    ImageNode(images[1]),
                    ImageNode(images[2]),
                ],
                weights=weights,
            )

        # --- FALL 2: PLL (Eins hochkant, zwei quer) ---
        if p_count == 4:
            return SplitNode(
                direction="horizontal",
                children=[
                    SplitNode(
                        direction="vertical",
                        children=[
                            ImageNode(images[0]),
                            ImageNode(images[1]),
                        ],
                        weights=[weights[0], weights[1]],
                    ),
                    ImageNode(images[2]),
                ],
                weights=[(weights[0] + weights[1]) / 2, weights[2]],
            )

        # --- FALL 3: mixed (1P2L / 2P1L) ---
        if p_count in (1, 2):
            portraits = []
            landscapes = []

            for img, p, w in zip(images, is_portrait, weights):
                if p:
                    portraits.append((img, w))
                else:
                    landscapes.append((img, w))

            # --- FALL: 1 Portrait + 2 Landscape ---
            if len(portraits) == 1 and len(landscapes) == 2:
                p_img, p_w = portraits[0]
                l1, l2 = landscapes

                return SplitNode(
                    direction="vertical",
                    children=[
                        ImageNode(p_img),
                        SplitNode(
                            direction="horizontal",
                            children=[
                                ImageNode(l1[0]),
                                ImageNode(l2[0]),
                            ],
                            weights=[l1[1], l2[1]],
                        ),
                    ],
                    weights=[p_w, (l1[1] + l2[1]) / 3],
                )

            # --- FALL: 2 Portrait + 1 Landscape ---
            if len(portraits) == 2 and len(landscapes) == 1:
                l_img, l_w = landscapes[0]
                p1, p2 = portraits

                return SplitNode(
                    direction="horizontal",
                    children=[
                        SplitNode(
                            direction="vertical",
                            children=[
                                ImageNode(p1[0]),
                                ImageNode(p2[0]),
                            ],
                            weights=[p1[1], p2[1]],
                        ),
                        ImageNode(l_img),
                    ],
                    weights=[p1[1] + p2[1], l_w],
                )

        # fallback symmetric
        return SplitNode(
            direction="horizontal",
            children=[
                ImageNode(images[0]),
                SplitNode(
                    direction="vertical",
                    children=[
                        ImageNode(images[1]),
                        ImageNode(images[2]),
                    ],
                    weights=[weights[1], weights[2]],
                ),
            ],
            weights=[weights[0], weights[1] + weights[2]],
        )

    def _generateLayout(self, images, target_width, target_height):
        """
        Erzeugt ein stabil balanciertes Layout basierend auf echter Partitionierung
        statt greedy rekursiven Splits.
        """

        n = len(images)

        if n == 1:
            return ImageNode(images[0])

        if n == 2:
            return self._generateTwoImageLayout(images, target_width, target_height)

        if n == 3:
            return self._chooseBestThreeLayout(images, target_width, target_height)

        # Special handling for 4 images: prefer nested/grouped layouts similar to
        # PhotoCollage.makeCollage. This results in nicer, more balanced
        # compositions (e.g. portrait on one side and three landscapes stacked
        # on the other, or two nested groups of two images).
        portraits = [img for img in images if img.width < img.height]
        landscapes = [img for img in images if img.width >= img.height]
        if n == 4 and len(portraits) == 1 and True:
            # Helper to compute weight for a group (sum of image weights)
            def group_weight(img_list):
                return sum(self._calculateLayoutWeight(img) for img in img_list)

            # Case: 1 portrait and 3 landscapes -> portrait on one side and
            # 3 images arranged (stacked or split) on the other side.
            if len(portraits) == 1 and len(landscapes) == 3:
                p_img = portraits[0]
                right_node = self._chooseBestThreeLayout(landscapes, target_width, target_height)
                left_node = ImageNode(p_img)
                # choose split direction according to canvas ratio
                direction = "vertical" if target_width >= target_height else "horizontal"
                return SplitNode(
                    direction=direction,
                    children=[left_node, right_node],
                    weights=[self._calculateLayoutWeight(p_img) * 7, group_weight(landscapes)],
                )

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

        for idx, row in enumerate(rows):
            row = self._balance_row(row)

            if (idx + len(row)) % 2 == 0:
                row = list(reversed(row))

            if len(row) == 1:
                row_nodes.append(ImageNode(row[0]))
                # TODO  row_weights.append(self._calculateLayoutWeight(row[0]))
                row_weights.append(sum([self._calculateLayoutWeight(img) for img in row]))
            else:
                w = self._adjust_row_weights(row)
                row_nodes.append(
                    SplitNode(
                        direction="vertical",
                        children=[ImageNode(img) for img in row],
                        weights=w,
                    )
                )
                row_weights.append(sum(w))

        # Falls nur eine Zeile → direkt zurück
        if len(row_nodes) == 1:
            return row_nodes[0]

        return SplitNode(direction="horizontal", children=row_nodes, weights=row_weights)

    def _interleave_portrait_landscape(self, images):
        portraits = [img for img in images if img.width < img.height]
        landscapes = [img for img in images if img.width >= img.height]

        result = []

        while portraits or landscapes:
            if landscapes:
                result.append(landscapes.pop(0))
            if portraits:
                result.append(portraits.pop(0))

        return result

    def _balance_row(self, row_images):
        portraits = deque([img for img in row_images if img.width < img.height])
        landscapes = deque([img for img in row_images if img.width >= img.height])

        def score(pattern):
            pt = len(portraits)
            ls = len(landscapes)
            needed_pt = pattern.count("P")
            needed_ls = pattern.count("L")

            # harte Strafe wenn nicht erfüllbar
            if needed_pt > pt or needed_ls > ls:
                return float("-inf")

            # leichte Präferenz für "symmetrische" Muster
            imbalance = abs(needed_pt - needed_ls)
            return -(imbalance)

        best = max(PATTERNS, key=score)

        result = []
        for t in best:
            if t == "P" and portraits:
                result.append(portraits.popleft())
            elif t == "L" and landscapes:
                result.append(landscapes.popleft())

        # Rest anhängen (fallback, falls mehr Bilder da sind)
        while portraits or landscapes:
            if landscapes:
                result.append(landscapes.popleft())
            if portraits:
                result.append(portraits.popleft())

        return result

    def _renderLayout(self, collage, node, x, y, width, height):
        # Leaf
        if isinstance(node, ImageNode):
            img = self._cropAndResize(node.image, width, height)
            img = self._applyRoundedCorners(img)
            pos = (int(x), int(y))
            if "A" in img.getbands():
                collage.paste(img, pos, img)
            else:
                collage.paste(img, pos)
            return

        if not node.children:
            return

        weight_sum = sum(node.weights) if node.weights else len(node.children)

        # --- VERTICAL SPLIT (nebeneinander) ---
        if node.direction == "vertical":
            total_spacing = self.spacing * (len(node.children) - 1)
            usable_width = width - total_spacing

            current_x = x

            for i, child in enumerate(node.children):
                w = node.weights[i] if node.weights else 1
                w_ratio = w / weight_sum

                if i == len(node.children) - 1:
                    cw = (x + width) - current_x  # Rest füllen
                else:
                    cw = int(usable_width * w_ratio)

                self._renderLayout(collage, child, current_x, y, cw, height)

                current_x += cw + self.spacing

            return

        # --- VERTICAL = OBEN/UNTEN ---
        current_y = y

        for i, child in enumerate(node.children):
            total_spacing = self.spacing * (len(node.children) - 1)
            usable_height = height - total_spacing

            h = node.weights[i] if node.weights else 1
            h_ratio = h / weight_sum

            if i == len(node.children) - 1:
                ch = (x + width) - current_y  # Rest füllen
            else:
                ch = int(usable_height * h_ratio)

            if i == len(node.children) - 1:
                ch = y + height - current_y

            self._renderLayout(collage, child, x, current_y, width, ch)

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

        images = self._interleave_portrait_landscape(images)

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

    def _adjust_row_weights(self, row_images):
        """
        Compute per-image weights for a row by combining the dynamic
        layout weight (from `_calculateLayoutWeight`) with an aspect-ratio
        modifier.

        The result preserves relative proportions (no forced normalization)
        so callers can continue to use `sum(weights)` to determine row
        contribution when building the parent SplitNode.

        Args:
            row_images: list of PIL Image objects that belong to the same row.

        Returns:
            A list of positive floats representing per-image weights for the
            row. Larger values indicate a larger share of space.
        """
        weights: list[float] = []

        for img in row_images:
            # base dynamic weight considers aspect ratio and image score
            base_weight = float(self._calculateLayoutWeight(img))

            # aspect modifier: keep previous behavior (pull portraits towards square)
            # but express it as a multiplier
            ratio = img.width / img.height
            if ratio < 1.0:
                aspect_mod = 0.7 + (ratio * 0.3)
            else:
                aspect_mod = ratio

            # combine both contributions
            combined = aspect_mod * (1 + base_weight / 10)

            # ensure strictly positive
            if combined <= 0:
                combined = 0.001

            weights.append(combined)

        return weights

    def _calculateImageScore(self, image):
        """
        Calculates a score in the range [0, 100),
        approaching 100 asymptotically as more relevant
        objects are detected.
        """
        if not self.detector:
            self.logger.info("Object detector not initialized, returning score 0.")
            return 0.0

        detections = self.detector.detect(image)
        self.logger.info(f"Calculating score for image with {len(detections)} detections.")

        weighted_sum = 0.0

        weights = {
            "person": 3.0,
            "dog": 2.0,
            "cat": 2.0,
            "bicycle": 1.5,
            "car": 1.5,
            "motorcycle": 1.5,
        }

        for d in detections:
            weight = weights.get(d.class_name, 0.5)
            contribution = weight * d.confidence

            weighted_sum += contribution

            self.logger.debug(
                f"Object '{d.class_name}' "
                f"(confidence={d.confidence:.2f}, "
                f"weight={weight:.1f}) "
                f"contribution={contribution:.2f}"
            )

        # Asymptotisch gegen 100
        score = 100.0 * (1.0 - math.exp(-weighted_sum / 10.0))

        self.logger.info(f"Weighted sum={weighted_sum:.2f}, score={score:.2f}")

        return round(score, 2)
