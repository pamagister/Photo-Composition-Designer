import random
from logging import Logger

import numpy as np
from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image, UnidentifiedImageError

from Photo_Composition_Designer.image.ObjectDetector import ObjectDetector
from Photo_Composition_Designer.image.SmartCrop import SmartCrop


class CollageRenderer:
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

    def generate(self, images: list[Image.Image]) -> Image.Image:
        """
        Ordnet die Bilder in der Composition an. Bilder werden vorab auf Lesbarkeit geprüft.
        """
        if not images:
            return Image.new(mode="RGB", size=(self.width, self.height), color=self.color)

        # Bilder nach Seitenverhältnis sortieren
        collage: Image.Image = Image.new(
            mode="RGB", size=(self.width, self.height), color=self.color
        )
        images = self.sortByAspectRatio(images)
        formats = self.analyzeImages(images)

        try:
            # Anordnungslogik basierend auf Bildanzahl
            if len(images) == 1:
                self.arrangeOneImage(collage, images[0], self.width, self.height)
            elif len(images) == 2:
                self.arrangeTwoImages(collage, images, formats, self.width, self.height)
            elif len(images) == 3:
                self.arrangeThreeImages(collage, images, formats, self.width, self.height)
            elif len(images) == 4:
                self.arrangeFourImages(collage, images, formats, self.width, self.height)
            elif len(images) == 5:
                self.arrangeFiveImages(collage, images, formats, self.width, self.height)
            else:
                self.arrangeMultipleImages(collage, images, self.width, self.height)
        except (UnidentifiedImageError, OSError) as e:
            self.logger.critical(f"Error in the arrangement of images: {e}")
            # Entferne ungültige Bilder und versuche es erneut
            valid_images = self.remove_invalid_images(images)
            if valid_images and len(valid_images) < len(images):
                self.logger.warning("Invalid images removed, try again...")
                return self.generate(valid_images)
            else:
                # Wenn keine gültigen Bilder mehr vorhanden sind, Fehler erneut werfen
                self.logger.warning("No more valid images available.")
                raise e
        return collage

    def remove_invalid_images(self, images: list[Image.Image]):
        """
        Überprüft eine Liste von Bildern und entfernt nicht lesbare oder kaputte Bilder.
        """
        valid_images = []
        for img in images:
            try:
                # Teste, ob das Bild ohne Fehler zugeschnitten werden kann
                img.crop((0, 0, 1, 1))
                valid_images.append(img)
            except (UnidentifiedImageError, OSError, AttributeError) as e:
                self.logger.info(f"Invalid image skipped: {e}")

        return valid_images

    @staticmethod
    def analyzeImages(images):
        """
        Analysiert, ob Bilder Hoch- oder Querformat haben.
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
    def sortByAspectRatio(images):
        """
        Sortiert Bilder basierend auf ihrem Seitenverhältnis (Breite / Höhe).
        Schmalste ("portrait") zuerst, breiteste ("landscape") zuletzt.
        """
        return sorted(images, key=lambda img: img.size[0] / img.size[1], reverse=False)

    def cropAndResize(self, image, target_width, target_height):
        """
        Schneidet ein Bild proportional zu und skaliert es dann auf die gewünschte Größe.
        Versucht dabei, erkannte Objekte im Bild zu behalten.
        """

        detections = None

        if self.detector:
            detections = self.detector.detect(image)

        return self.cropper.crop(
            image=image,
            target_width=target_width,
            target_height=target_height,
            detections=detections,
        )

    def detect_objects(self, image: Image.Image) -> list[dict]:
        """
        Detect objects using YOLO ONNX.
        Returns:
            [
                {
                    "bbox": [x1, y1, x2, y2],
                    "confidence": 0.95
                }
            ]
        """

        wanted_ids = {
            0,  # person
            1,  # bicycle
            2,  # car
            3,  # motorcycle
            4,  # airplane
            5,  # bus
            8,  # boat
            14,  # bird
            15,  # cat
            16,  # dog
            17,  # horse
            18,  # sheep
            19,  # cow
        }

        id_map = {
            0: "person",
            1: "bicycle",
            2: "car",
            3: "motorcycle",
            4: "airplane",
            5: "bus",
            6: "train",
            7: "truck",
            8: "boat",
            9: "traffic light",
            10: "fire hydrant",
            11: "stop sign",
            12: "parking meter",
            13: "bench",
            14: "bird",
            15: "cat",
            16: "dog",
            17: "horse",
            18: "sheep",
            19: "cow",
            20: "elephant",
            21: "bear",
            22: "zebra",
            23: "giraffe",
            24: "backpack",
            25: "umbrella",
            26: "handbag",
            27: "tie",
            28: "suitcase",
            29: "frisbee",
            30: "skis",
            31: "snowboard",
            32: "sports ball",
            33: "kite",
            34: "baseball bat",
            35: "baseball glove",
            36: "skateboard",
            37: "surfboard",
            38: "tennis racket",
            39: "bottle",
            40: "wine glass",
            41: "cup",
            42: "fork",
            43: "knife",
            44: "spoon",
            45: "bowl",
            46: "banana",
            47: "apple",
            48: "sandwich",
            49: "orange",
            50: "broccoli",
            51: "carrot",
            52: "hot dog",
            53: "pizza",
            54: "donut",
            55: "cake",
            56: "chair",
            57: "couch",
            58: "potted plant",
            59: "bed",
            60: "dining table",
            61: "toilet",
            62: "tv",
            63: "laptop",
            64: "mouse",
            65: "remote",
            66: "keyboard",
            67: "cell phone",
            68: "microwave",
            69: "oven",
            70: "toaster",
            71: "sink",
            72: "refrigerator",
            73: "book",
            74: "clock",
            75: "vase",
            76: "scissors",
            77: "teddy bear",
            78: "hair drier",
            79: "toothbrush",
        }

        input_name = self.yolo_session.get_inputs()[0].name

        orig_w, orig_h = image.size

        # Resize to model input size
        resized = image.resize((640, 640))
        img = np.array(resized, dtype=np.float32)

        # RGB -> float32 [0..1]
        img /= 255.0

        # HWC -> CHW
        img = np.transpose(img, (2, 0, 1))

        # Add batch dimension
        img = np.expand_dims(img, axis=0)
        self.logger.debug(f"Process image {input_name} with object recognition.")
        outputs = self.yolo_session.run(None, {input_name: img})

        detections = outputs[0][0]

        scale_x = orig_w / 640.0
        scale_y = orig_h / 640.0

        objects = []

        for det in detections:
            x1, y1, x2, y2, conf, cls_id = det
            cls_id = int(cls_id)
            if conf < 0.25:
                continue
            if cls_id not in wanted_ids:
                continue

            self.logger.info(f"Object detected: {id_map.get(cls_id)}: {conf}")

            objects.append(
                {
                    "bbox": [
                        float(x1 * scale_x),
                        float(y1 * scale_y),
                        float(x2 * scale_x),
                        float(y2 * scale_y),
                    ],
                    "confidence": float(conf),
                }
            )

        return objects

    def calculateImageScore(
        self,
        image,
    ):

        if not self.detector:
            return 0

        score = 0

        detections = self.detector.detect(image)

        for d in detections:
            if d.class_name == "person":
                score += 5

            elif d.class_name in ("dog", "cat"):
                score += 4

            elif d.class_name == "bicycle":
                score += 3

            elif d.class_name in ("car", "motorcycle"):
                score += 2

        return score

    def arrangeOneImage(self, collage, image, width, height):
        """
        Layout für ein einzelnes Bild.
        """
        img = self.cropAndResize(image, width, height)
        collage.paste(img, (0, 0))

    def arrangeTwoImages(self, collage, images, formats, width, height):
        """
        Layout für zwei Bilder.
        """
        if "portrait" in formats:
            portrait_idx = formats.index("portrait")
            landscape_idx = 1 - portrait_idx
            # Goldener Schnitt Layout
            portrait_width = int(width * 0.4)
            landscape_width = width - portrait_width - self.spacing
            img1 = self.cropAndResize(images[portrait_idx], portrait_width, height)
            img2 = self.cropAndResize(images[landscape_idx], landscape_width, height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (portrait_width + self.spacing, 0))
        else:
            # Beide Querformat -> nebeneinander
            img_width = (width - self.spacing) // 2
            img1 = self.cropAndResize(images[0], img_width, height)
            img2 = self.cropAndResize(images[1], img_width, height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (img_width + self.spacing, 0))

    def arrangeThreeImages(self, collage, images, formats, w, h):
        """
        Layouts für drei Bilder.
        """
        s = self.spacing
        layouts = [
            # Ein großes Bild quer oben, zwei kleinere unten nebeneinander LLL
            lambda imgs: [
                (self.cropAndResize(imgs[0], w, int(h * 0.6) - s), (0, 0)),
                (
                    self.cropAndResize(imgs[1], int(w * 0.5), int(h * 0.4)),
                    (0, int(h * 0.6)),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.5), int(h * 0.4)),
                    (int(w * 0.5) + s, int(h * 0.6)),
                ),
            ],
            # Großes Querformat links, zwei Querformat rechts übereinander LLL
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.7), h), (0, 0)),
                (
                    self.cropAndResize(imgs[1], int(w * 0.3), int(h * 0.5)),
                    (int(w * 0.7) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.3), int(h * 0.5) - s),
                    (int(w * 0.7) + s, int(h * 0.5) + s),
                ),
            ],
            # Großes Hochformat links, zwei Querformat rechts übereinander PLL
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.4), h), (0, 0)),
                (
                    self.cropAndResize(imgs[1], int(w * 0.6), int(h * 0.5)),
                    (int(w * 0.4) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.6), int(h * 0.5) - s),
                    (int(w * 0.4) + s, int(h * 0.5) + s),
                ),
            ],
            # Großes Querformat links, zwei Hochformat rechts übereinander PPL
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.6), h), (0, 0)),
                (
                    self.cropAndResize(imgs[1], int(w * 0.4), int(h * 0.5)),
                    (int(w * 0.6) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.4), int(h * 0.5) - s),
                    (int(w * 0.6) + s, int(h * 0.5) + s),
                ),
            ],
        ]

        if formats.count("portrait") == 0:
            random.seed()
            if random.random() > 0.8:
                layout = layouts[0]
            else:
                layout = layouts[1]
        elif formats.count("portrait") == 1:
            layout = layouts[2]
        elif formats.count("portrait") == 2:
            layout = layouts[3]
        else:
            # Drei gleich große Bilder im Hochformat nebeneinander PPP
            self.arrangeMultipleImages(collage, images, self.width, self.height)
            return

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrangeFourImages(self, collage, images, formats, w, h):
        """
        Layouts für vier Bilder.
        """
        s = self.spacing
        layouts = [
            # Zwei große Bilder oben, zwei etwas kleiner unten, leicht versetzt (LLLL)
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.45), int(h * 0.55) - s), (0, 0)),
                (
                    self.cropAndResize(imgs[3], int(w * 0.55), int(h * 0.55) - s),
                    (int(w * 0.45) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.55), int(h * 0.45)),
                    (0, int(h * 0.55)),
                ),
                (
                    self.cropAndResize(imgs[1], int(w * 0.45), int(h * 0.45)),
                    (int(w * 0.55) + s, int(h * 0.55)),
                ),
            ],
            # Großes Quadrat, drei kleine landscape rechts Q-LLL
            lambda imgs: [
                (
                    self.cropAndResize(imgs[0], int(w * 0.7), h),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self.cropAndResize(imgs[1], int(w * 0.3), int(h / 3)),
                    (int(w * 0.7) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.3), int(h / 3) - s),
                    (int(w * 0.7) + s, int(h / 3) + s),
                ),
                (
                    self.cropAndResize(imgs[3], int(w * 0.3), int(h / 3) - 1 * s),
                    (int(w * 0.7) + s, int(h * 2 / 3) + s),
                ),
            ],
            # Großes portrait-Bild links, rechts oben landscape,
            # darunter zwei kleine landscape nebeneinander PLLL
            lambda imgs: [
                (
                    self.cropAndResize(imgs[0], int(w * 0.4), h),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self.cropAndResize(imgs[1], int(w * 0.6), int(h * 3 / 5)),
                    (int(w * 0.4) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.3 - s), int(h * 2 / 5) - s),
                    (int(w * 0.4) + s, int(h * 3 / 5) + s),
                ),
                (
                    self.cropAndResize(imgs[3], int(w * 0.3 - s), int(h * 2 / 5) - s),
                    (int(w * 0.7) + s, int(h * 3 / 5) + s),
                ),
            ],
            # Großes portrait-Bild links, rechts oben landscape,
            # darunter kleines portrait und landscape PPLL
            lambda imgs: [
                (
                    self.cropAndResize(imgs[0], int(w * 0.4), h),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self.cropAndResize(imgs[2], int(w * 0.6), int(h * 3 / 5)),
                    (int(w * 0.4) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[1], int(w * 0.2), int(h * 2 / 5) - s),
                    (int(w * 0.4) + s, int(h * 3 / 5) + s),
                ),
                (
                    self.cropAndResize(imgs[3], int(w * 0.4 - 2 * s), int(h * 2 / 5) - s),
                    (int(w * 0.6) + 2 * s, int(h * 3 / 5) + s),
                ),
            ],
            # Großes portrait-Bild links, rechts oben landscape,
            # darunter zwei kleines portrait nebeneinander PPLL
            lambda imgs: [
                (
                    self.cropAndResize(imgs[0], int(w * 0.4), h),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self.cropAndResize(imgs[3], int(w * 0.6), int(h * 2 / 5)),
                    (int(w * 0.4) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[1], int(w * 0.25), int(h * 3 / 5) - s),
                    (int(w * 0.4) + s, int(h * 2 / 5) + s),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.35 - 2 * s), int(h * 3 / 5) - s),
                    (int(w * 0.65) + 2 * s, int(h * 2 / 5) + s),
                ),
            ],
        ]

        if formats.count("portrait") == 0:  # LLLL = 4x landscape
            random.seed()
            if random.random() > 0.5:
                layout = layouts[0]
            else:
                layout = layouts[1]
        elif formats.count("portrait") == 1:  # PLLL
            layout = layouts[2]
        elif formats.count("portrait") == 2:  # PPLL
            layout = layouts[3]
        else:  # PPPL
            layout = layouts[4]

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrangeFiveImages(self, collage, images, formats, w, h):
        """
        Layouts für fünf Bilder.
        """
        s = self.spacing
        layouts = [
            # Zwei große Bilder oben, drei etwas kleinere unten (LLLLL)
            lambda imgs: [
                (
                    self.cropAndResize(imgs[0], int(w * 0.5), int(h * 0.6) - s),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self.cropAndResize(imgs[1], int(w * 0.5), int(h * 0.6) - s),
                    (int(w * 0.5) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w / 3), int(h * 0.4)),
                    (int(w * 0 / 3) + 0 * s, int(h * 0.6)),
                ),
                (
                    self.cropAndResize(imgs[3], int(w / 3), int(h * 0.4)),
                    (int(w * 1 / 3) + 1 * s, int(h * 0.6)),
                ),
                (
                    self.cropAndResize(imgs[4], int(w / 3), int(h * 0.4)),
                    (int(w * 2 / 3) + 2 * s, int(h * 0.6)),
                ),
            ],
            # Links ein großes Portrait,
            # rechts daneben im goldenen Schnitt vier kleinere Bilder (PLLLL)
            lambda imgs: [
                (
                    self.cropAndResize(imgs[0], int(w * 0.3 - s), int(h)),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self.cropAndResize(imgs[1], int(w * 0.3), int(h * 0.55) - s),
                    (int(w * 0.3), 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.40) - s, int(h * 0.55) - s),
                    (int(w * 0.6) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[3], int(w * 0.40), int(h * 0.45)),
                    (int(w * 0.3), int(h * 0.55)),
                ),
                (
                    self.cropAndResize(imgs[4], int(w * 0.3) - s, int(h * 0.45)),
                    (int(w * 0.7) + s, int(h * 0.55)),
                ),
            ],
            # zwei große aber dennoch leider recht breite Portrais oben,
            # unten drei kleine landscape  (PPLLL)
            lambda imgs: [
                (
                    self.cropAndResize(imgs[0], int(w * 0.5), int(h * 2 / 3) - s),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self.cropAndResize(imgs[1], int(w * 0.5), int(h * 2 / 3) - s),
                    (int(w * 0.5) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[4], int(w / 3), int(h / 3)),
                    (int(w * 0 / 3) + 0 * s, int(h * 2 / 3)),
                ),
                (
                    self.cropAndResize(imgs[3], int(w / 3), int(h / 3)),
                    (int(w * 1 / 3) + 1 * s, int(h * 2 / 3)),
                ),
                (
                    self.cropAndResize(imgs[2], int(w / 3), int(h / 3)),
                    (int(w * 2 / 3) + 2 * s, int(h * 2 / 3)),
                ),
            ],
            # Links ein großes Portrait, rechts daneben im goldenen Schnitt
            # vier kleinere Bilder kleine unten (PPPLL)
            lambda imgs: [
                (
                    self.cropAndResize(imgs[0], int(w * 0.35 - s), int(h)),
                    (0, 0),
                ),  # portrait, index 0
                (
                    self.cropAndResize(imgs[1], int(w * 0.25), int(h * 0.55) - s),
                    (int(w * 0.35), 0),
                ),
                (
                    self.cropAndResize(imgs[2], int(w * 0.40) - s, int(h * 0.55) - s),
                    (int(w * 0.6) + s, 0),
                ),
                (
                    self.cropAndResize(imgs[3], int(w * 0.40), int(h * 0.45)),
                    (int(w * 0.35), int(h * 0.55)),
                ),
                (
                    self.cropAndResize(imgs[4], int(w * 0.25) - s, int(h * 0.45)),
                    (int(w * 0.75) + s, int(h * 0.55)),
                ),
            ],
        ]

        if formats.count("portrait") == 0:  # LLLLL = 5x landscape
            layout = layouts[0]
        elif formats.count("portrait") == 1:  # PLLLL
            layout = layouts[1]
        elif formats.count("portrait") == 2:  # PPLLL
            layout = layouts[2]
        else:  # PPPLL
            layout = layouts[3]

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrangeMultipleImages(self, collage, images, width, height):
        """
        Raster-Layout für mehr als vier Bilder, mit gleichmäßiger Verteilung.
        Passt automatisch die Anzahl der Zeilen und Spalten an.
        """
        # Bestimme die Anzahl der Spalten und Zeilen basierend auf der Anzahl der Bilder
        rows = int(len(images) ** 0.5)  # Quadratwurzel für möglichst gleichmäßige Aufteilung
        cols = (len(images) + rows - 1) // rows  # Rundung nach oben

        # Berechnung der Zellgrößen basierend auf der Composition-Größe und Abstände
        cell_width = (width - (cols - 1) * self.spacing) // cols
        cell_height = (height - (rows - 1) * self.spacing) // rows

        # Bilder in das Raster einfügen
        for i, img in enumerate(images):
            # Bestimme Zeile und Spalte des aktuellen Bildes
            row = i // cols
            col = i % cols

            # Passe die Bildgröße an die Rasterzelle an
            resized_img = self.cropAndResize(img, cell_width, cell_height)

            # Berechne die Position des Bildes in der Composition
            x_offset = col * (cell_width + self.spacing)
            y_offset = row * (cell_height + self.spacing)

            # Füge das Bild in die Composition ein
            collage.paste(resized_img, (x_offset, y_offset))
