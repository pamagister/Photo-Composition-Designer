import random
from logging import Logger

from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image, UnidentifiedImageError

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.image.SmartCrop import SmartCrop


class CollageRenderer:
    """
    Renders a collage of images with various layout options,
    optionally using object recognition for smart cropping.
    """

    def __init__(
        self, width=900, height=600, spacing=10, color=(0, 0, 0), use_object_recognition=False
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

    def generate(self, images: list[Image.Image]) -> Image.Image:
        """
        Arranges the images in the composition. Images are checked for readability beforehand.
        """
        self.logger.info(f"Starting collage generation for {len(images)} images.")

        if not images:
            self.logger.info("No images provided, returning empty collage.")
            return Image.new(mode="RGB", size=(self.width, self.height), color=self.color)

        collage: Image.Image = Image.new(
            mode="RGB", size=(self.width, self.height), color=self.color
        )
        images = self._sortByAspectRatio(images)
        self.logger.info("Images sorted by aspect ratio.")
        formats = self._analyzeImages(images)
        self.logger.info(f"Image formats analyzed: {formats}")

        try:
            # Arrangement logic based on the number of images
            num_images = len(images)
            self.logger.info(f"Arranging {num_images} images.")

            if num_images == 1:
                self._arrangeOneImage(collage, images[0], self.width, self.height)
            elif num_images == 2:
                self._arrangeTwoImages(collage, images, formats, self.width, self.height)
            elif num_images == 3:
                self._arrangeThreeImages(collage, images, formats, self.width, self.height)
            elif num_images == 4:
                self._arrangeFourImages(collage, images, formats, self.width, self.height)
            elif num_images == 5:
                self._arrangeFiveImages(collage, images, formats, self.width, self.height)
            else:
                self._arrangeMultipleImages(collage, images, self.width, self.height)
            self.logger.info("Image arrangement completed successfully.")

        except (UnidentifiedImageError, OSError) as e:
            self.logger.info(
                f"Error in the arrangement of images: {e}. Attempting to remove invalid images."
            )
            # Remove invalid images and try again
            valid_images = self._remove_invalid_images(images)
            if valid_images and len(valid_images) < len(images):
                self.logger.info(
                    "Invalid images removed, trying collage generation again with valid images."
                )
                return self.generate(valid_images)
            else:
                # If no valid images remain, re-raise the error
                self.logger.info("No more valid images available after removal.")
                raise e
        return collage

    def _remove_invalid_images(self, images: list[Image.Image]):
        """
        Checks a list of images and removes unreadable or corrupted images.
        """
        valid_images = []
        for img in images:
            try:
                # Test if the image can be cropped without errors
                img.crop((0, 0, 1, 1))
                valid_images.append(img)
            except (UnidentifiedImageError, OSError, AttributeError) as e:
                self.logger.info(f"Invalid image skipped: {e}")

        return valid_images

    @staticmethod
    def _analyzeImages(images):
        """
        Analyzes whether images are portrait or landscape.
        """
        analysis = []
        for img in images:
            width, height = img.size
            if height > width:
                analysis.append("portrait")
            else:
                analysis.append("landscape")
        return analysis

    @staticmethod
    def _sortByAspectRatio(images):
        """
        Sorts images based on their aspect ratio (width / height).
        Narrowest ("portrait") first, widest ("landscape") last.
        """
        return sorted(images, key=lambda img: img.size[0] / img.size[1], reverse=False)

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

    def _arrangeOneImage(self, collage, image, width, height):
        """
        Layout for a single image.
        """
        self.logger.info("Arranging one image.")
        img = self._cropAndResize(image, width, height)
        collage.paste(img, (0, 0))

    def _arrangeTwoImages(self, collage, images, formats, width, height):
        """
        Layout for two images.
        """
        self.logger.info("Arranging two images.")
        if "portrait" in formats:
            self.logger.info("Two images: one portrait, one landscape layout.")
            portrait_idx = formats.index("portrait")
            landscape_idx = 1 - portrait_idx
            # Golden ratio layout
            portrait_width = int(width * 0.4)
            landscape_width = width - portrait_width - self.spacing
            img1 = self._cropAndResize(images[portrait_idx], portrait_width, height)
            img2 = self._cropAndResize(images[landscape_idx], landscape_width, height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (portrait_width + self.spacing, 0))
        else:
            self.logger.info("Two images: both landscape layout (side-by-side).")
            # Both landscape -> side by side
            img_width = (width - self.spacing) // 2
            img1 = self._cropAndResize(images[0], img_width, height)
            img2 = self._cropAndResize(images[1], img_width, height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (img_width + self.spacing, 0))

    def _arrangeThreeImages(self, collage, images, formats, w, h):
        """
        Layouts for three images.
        """
        self.logger.info("Arranging three images.")
        s = self.spacing
        layouts = [
            # One large landscape image at the top,
            # two smaller ones side-by-side at the bottom (LLL)
            lambda imgs: [
                (self._cropAndResize(imgs[0], w, int(h * 0.6) - s), (0, 0)),
                (
                    self._cropAndResize(imgs[1], int(w * 0.5), int(h * 0.4)),
                    (0, int(h * 0.6)),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.5), int(h * 0.4)),
                    (int(w * 0.5) + s, int(h * 0.6)),
                ),
            ],
            # Large landscape on the left, two landscape images stacked on the right (LLL)
            lambda imgs: [
                (self._cropAndResize(imgs[0], int(w * 0.7), h), (0, 0)),
                (
                    self._cropAndResize(imgs[1], int(w * 0.3), int(h * 0.5)),
                    (int(w * 0.7) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.3), int(h * 0.5) - s),
                    (int(w * 0.7) + s, int(h * 0.5) + s),
                ),
            ],
            # Large portrait on the left, two landscape images stacked on the right (PLL)
            lambda imgs: [
                (self._cropAndResize(imgs[0], int(w * 0.4), h), (0, 0)),
                (
                    self._cropAndResize(imgs[1], int(w * 0.6), int(h * 0.5)),
                    (int(w * 0.4) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.6), int(h * 0.5) - s),
                    (int(w * 0.4) + s, int(h * 0.5) + s),
                ),
            ],
            # Large landscape on the left, two portrait images stacked on the right (PPL)
            lambda imgs: [
                (self._cropAndResize(imgs[0], int(w * 0.6), h), (0, 0)),
                (
                    self._cropAndResize(imgs[1], int(w * 0.4), int(h * 0.5)),
                    (int(w * 0.6) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.4), int(h * 0.5) - s),
                    (int(w * 0.6) + s, int(h * 0.5) + s),
                ),
            ],
        ]

        if formats.count("portrait") == 0:  # LLL = 3x landscape
            self.logger.info("Three images: all landscape layout.")
            random.seed()
            if random.random() > 0.8:
                layout = layouts[0]
                self.logger.info("Applying LLL layout (one large top, two small bottom).")
            else:
                layout = layouts[1]
                self.logger.info("Applying LLL layout (large left, two stacked right).")
        elif formats.count("portrait") == 1:  # PLL
            self.logger.info("Three images: one portrait, two landscape layout.")
            layout = layouts[2]
            self.logger.info("Applying PLL layout.")
        elif formats.count("portrait") == 2:  # PPL
            self.logger.info("Three images: two portrait, one landscape layout.")
            layout = layouts[3]
            self.logger.info("Applying PPL layout.")
        else:
            self.logger.info("Three images: all portrait layout (using multiple images grid).")
            # Three equally sized portrait images side by side PPP
            self._arrangeMultipleImages(collage, images, self.width, self.height)
            return

        for img, pos in layout(images):
            collage.paste(img, pos)

    def _arrangeFourImages(self, collage, images, formats, w, h):
        """
        Layouts for four images.
        """
        self.logger.info("Arranging four images.")
        s = self.spacing
        layouts = [
            # Two large images at the top,
            # two slightly smaller at the bottom, slightly offset (LLLL)
            lambda imgs: [
                (self._cropAndResize(imgs[0], int(w * 0.45), int(h * 0.55) - s), (0, 0)),
                (
                    self._cropAndResize(imgs[3], int(w * 0.55), int(h * 0.55) - s),
                    (int(w * 0.45) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.55), int(h * 0.45)),
                    (0, int(h * 0.55)),
                ),
                (
                    self._cropAndResize(imgs[1], int(w * 0.45), int(h * 0.45)),
                    (int(w * 0.55) + s, int(h * 0.55)),
                ),
            ],
            # Large square, three small landscape on the right Q-LLL
            lambda imgs: [
                (
                    self._cropAndResize(imgs[0], int(w * 0.7), h),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self._cropAndResize(imgs[1], int(w * 0.3), int(h / 3)),
                    (int(w * 0.7) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.3), int(h / 3) - s),
                    (int(w * 0.7) + s, int(h / 3) + s),
                ),
                (
                    self._cropAndResize(imgs[3], int(w * 0.3), int(h / 3) - 1 * s),
                    (int(w * 0.7) + s, int(h * 2 / 3) + s),
                ),
            ],
            # Large portrait image on the left, landscape at top right,
            # two small landscape side by side below PLLL
            lambda imgs: [
                (
                    self._cropAndResize(imgs[0], int(w * 0.4), h),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self._cropAndResize(imgs[1], int(w * 0.6), int(h * 3 / 5)),
                    (int(w * 0.4) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.3 - s), int(h * 2 / 5) - s),
                    (int(w * 0.4) + s, int(h * 3 / 5) + s),
                ),
                (
                    self._cropAndResize(imgs[3], int(w * 0.3 - s), int(h * 2 / 5) - s),
                    (int(w * 0.7) + s, int(h * 3 / 5) + s),
                ),
            ],
            # Large portrait image on the left, landscape at top right,
            # below it small portrait and landscape PPLL
            lambda imgs: [
                (
                    self._cropAndResize(imgs[0], int(w * 0.4), h),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self._cropAndResize(imgs[2], int(w * 0.6), int(h * 3 / 5)),
                    (int(w * 0.4) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[1], int(w * 0.2), int(h * 2 / 5) - s),
                    (int(w * 0.4) + s, int(h * 3 / 5) + s),
                ),
                (
                    self._cropAndResize(imgs[3], int(w * 0.4 - 2 * s), int(h * 2 / 5) - s),
                    (int(w * 0.6) + 2 * s, int(h * 3 / 5) + s),
                ),
            ],
            # Large portrait image on the left, landscape at top right,
            # below it two small portrait side by side PPLL
            lambda imgs: [
                (
                    self._cropAndResize(imgs[0], int(w * 0.4), h),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self._cropAndResize(imgs[3], int(w * 0.6), int(h * 2 / 5)),
                    (int(w * 0.4) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[1], int(w * 0.25), int(h * 3 / 5) - s),
                    (int(w * 0.4) + s, int(h * 2 / 5) + s),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.35 - 2 * s), int(h * 3 / 5) - s),
                    (int(w * 0.65) + 2 * s, int(h * 2 / 5) + s),
                ),
            ],
        ]

        if formats.count("portrait") == 0:  # LLLL = 4x landscape
            self.logger.info("Four images: all landscape layout.")
            random.seed()
            if random.random() > 0.5:
                layout = layouts[0]
                self.logger.info("Applying LLLL layout (two large top, two small bottom).")
            else:
                layout = layouts[1]
                self.logger.info("Applying LLLL layout (large square left, three small right).")
        elif formats.count("portrait") == 1:  # PLLL
            self.logger.info("Four images: one portrait, three landscape layout.")
            layout = layouts[2]
            self.logger.info("Applying PLLL layout.")
        elif formats.count("portrait") == 2:  # PPLL
            self.logger.info("Four images: two portrait, two landscape layout.")
            layout = layouts[3]
            self.logger.info(
                "Applying PPLL layout (large portrait left, "
                "landscape top right, portrait/landscape bottom)."
            )
        else:  # PPPL
            self.logger.info("Four images: three portrait, one landscape layout.")
            layout = layouts[4]
            self.logger.info("Applying PPPL layout.")

        for img, pos in layout(images):
            collage.paste(img, pos)

    def _arrangeFiveImages(self, collage, images, formats, w, h):
        """
        Layouts for five images.
        """
        self.logger.info("Arranging five images.")
        s = self.spacing
        layouts = [
            # Two large images at the top, three slightly smaller at the bottom (LLLLL)
            lambda imgs: [
                (
                    self._cropAndResize(imgs[0], int(w * 0.5), int(h * 0.6) - s),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self._cropAndResize(imgs[1], int(w * 0.5), int(h * 0.6) - s),
                    (int(w * 0.5) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w / 3), int(h * 0.4)),
                    (int(w * 0 / 3) + 0 * s, int(h * 0.6)),
                ),
                (
                    self._cropAndResize(imgs[3], int(w / 3), int(h * 0.4)),
                    (int(w * 1 / 3) + 1 * s, int(h * 0.6)),
                ),
                (
                    self._cropAndResize(imgs[4], int(w / 3), int(h * 0.4)),
                    (int(w * 2 / 3) + 2 * s, int(h * 0.6)),
                ),
            ],
            # Large portrait on the left, four smaller images on the right in golden ratio (PLLLL)
            lambda imgs: [
                (
                    self._cropAndResize(imgs[0], int(w * 0.3 - s), int(h)),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self._cropAndResize(imgs[1], int(w * 0.3), int(h * 0.55) - s),
                    (int(w * 0.3), 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.40) - s, int(h * 0.55) - s),
                    (int(w * 0.6) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[3], int(w * 0.40), int(h * 0.45)),
                    (int(w * 0.3), int(h * 0.55)),
                ),
                (
                    self._cropAndResize(imgs[4], int(w * 0.3) - s, int(h * 0.45)),
                    (int(w * 0.7) + s, int(h * 0.55)),
                ),
            ],
            # Two large but rather wide portraits at the top,
            # three small landscape at the bottom (PPLLL)
            lambda imgs: [
                (
                    self._cropAndResize(imgs[0], int(w * 0.5), int(h * 2 / 3) - s),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self._cropAndResize(imgs[1], int(w * 0.5), int(h * 2 / 3) - s),
                    (int(w * 0.5) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[4], int(w / 3), int(h / 3)),
                    (int(w * 0 / 3) + 0 * s, int(h * 2 / 3)),
                ),
                (
                    self._cropAndResize(imgs[3], int(w / 3), int(h / 3)),
                    (int(w * 1 / 3) + 1 * s, int(h * 2 / 3)),
                ),
                (
                    self._cropAndResize(imgs[2], int(w / 3), int(h / 3)),
                    (int(w * 2 / 3) + 2 * s, int(h * 2 / 3)),
                ),
            ],
            # Large portrait on the left, four smaller images on the right in golden ratio (PPPLL)
            lambda imgs: [
                (
                    self._cropAndResize(imgs[0], int(w * 0.35 - s), int(h)),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self._cropAndResize(imgs[1], int(w * 0.25), int(h * 0.55) - s),
                    (int(w * 0.35), 0),
                ),
                (
                    self._cropAndResize(imgs[2], int(w * 0.40) - s, int(h * 0.55) - s),
                    (int(w * 0.6) + s, 0),
                ),
                (
                    self._cropAndResize(imgs[3], int(w * 0.40), int(h * 0.45)),
                    (int(w * 0.35), int(h * 0.55)),
                ),
                (
                    self._cropAndResize(imgs[4], int(w * 0.25) - s, int(h * 0.45)),
                    (int(w * 0.75) + s, int(h * 0.55)),
                ),
            ],
        ]

        if formats.count("portrait") == 0:  # LLLLL = 5x landscape
            self.logger.info("Five images: all landscape layout.")
            layout = layouts[0]
            self.logger.info("Applying LLLLL layout.")
        elif formats.count("portrait") == 1:  # PLLLL
            self.logger.info("Five images: one portrait, four landscape layout.")
            layout = layouts[1]
            self.logger.info("Applying PLLLL layout.")
        elif formats.count("portrait") == 2:  # PPLLL
            self.logger.info("Five images: two portrait, three landscape layout.")
            layout = layouts[2]
            self.logger.info("Applying PPLLL layout.")
        else:  # PPPLL
            self.logger.info("Five images: three portrait, two landscape layout.")
            layout = layouts[3]
            self.logger.info("Applying PPPLL layout.")

        for img, pos in layout(images):
            collage.paste(img, pos)

    def _arrangeMultipleImages(self, collage, images, width, height):
        """
        Grid layout for more than four images, with even distribution.
        Automatically adjusts the number of rows and columns.
        """
        self.logger.info(f"Arranging {len(images)} images in a grid layout.")
        # Determine the number of columns and rows based on the number of images
        rows = int(len(images) ** 0.5)  # Square root for as even a distribution as possible
        cols = (len(images) + rows - 1) // rows  # Round up

        self.logger.info(f"Grid layout: {rows} rows, {cols} columns.")

        # Calculate cell sizes based on composition size and spacing
        cell_width = (width - (cols - 1) * self.spacing) // cols
        cell_height = (height - (rows - 1) * self.spacing) // rows

        # Insert images into the grid
        for i, img in enumerate(images):
            # Determine row and column of the current image
            row = i // cols
            col = i % cols

            # Adjust image size to the grid cell
            resized_img = self._cropAndResize(img, cell_width, cell_height)

            # Calculate the position of the image in the composition
            x_offset = col * (cell_width + self.spacing)
            y_offset = row * (cell_height + self.spacing)

            self.logger.info(
                f"Pasting image {i + 1} at ({x_offset}, {y_offset}) "
                f"with size ({cell_width}, {cell_height})."
            )
            # Paste the image into the composition
            collage.paste(resized_img, (x_offset, y_offset))
