from dataclasses import dataclass
from logging import Logger

import numpy as np
import onnxruntime as ort
from config_cli_gui.logging import get_logger, initialize_logging
from PIL import Image


@dataclass(slots=True)
class Detection:
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]


class ObjectDetector:
    """
    YOLO ONNX wrapper.
    """

    # https://docs.ultralytics.com/datasets/segment/coco#sample-images-and-annotations
    WANTED_CLASSES = {
        0: "person",
        1: "bicycle",
        2: "car",
        3: "motorcycle",
        4: "airplane",
        5: "bus",
        6: "train",
        15: "cat",
        16: "dog",
        17: "horse",
        18: "sheep",
        19: "cow",
        39: "bottle",
        40: "wine glass",
        41: "cup",
    }

    def __init__(
        self,
        model_path: str = "res/yolo/yolo26n.onnx",
        confidence_threshold: float = 0.25,
    ):
        initialize_logging()

        self.logger: Logger = get_logger("base")

        self.confidence_threshold = confidence_threshold

        self.session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )

        self.input_name = self.session.get_inputs()[0].name

    def detect(self, image: Image.Image) -> list[Detection]:

        orig_w, orig_h = image.size

        resized = image.resize((640, 640))

        img = np.asarray(resized, dtype=np.float32)
        img /= 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)

        outputs = self.session.run(
            None,
            {self.input_name: img},
        )

        detections = outputs[0][0]

        scale_x = orig_w / 640.0
        scale_y = orig_h / 640.0

        result: list[Detection] = []

        for det in detections:
            x1, y1, x2, y2, conf, cls_id = det

            cls_id = int(cls_id)

            if conf < self.confidence_threshold:
                continue

            if cls_id not in self.WANTED_CLASSES:
                continue

            class_name = self.WANTED_CLASSES[cls_id]

            self.logger.info(f"Object detected: {class_name}: {conf:.3f}")

            result.append(
                Detection(
                    class_name=class_name,
                    confidence=float(conf),
                    bbox=(
                        float(x1 * scale_x),
                        float(y1 * scale_y),
                        float(x2 * scale_x),
                        float(y2 * scale_y),
                    ),
                )
            )

        return result
