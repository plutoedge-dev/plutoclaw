"""
Detector - YOLOv8 wrapper
Auto: uses Hailo NPU if available, falls back to CPU
"""
import cv2
import logging
import time
from core.platform import has_hailo

logger = logging.getLogger("plutoclaw.detector")


class Detection:
    def __init__(self, class_name: str, confidence: float, box: list):
        self.class_name = class_name
        self.confidence = confidence
        self.box = box  # [x1, y1, x2, y2]

    def __repr__(self):
        return f"Detection({self.class_name}, {self.confidence:.2f})"


class YOLODetector:
    """
    YOLOv8 detector - supports any model from Ultralytics
    On Mac: runs on CPU/MPS
    On Pi + Hailo: runs on NPU (automatically)
    """

    def __init__(self, model_name: str = "yolov8n.pt", confidence: float = 0.5):
        self.model_name = model_name
        self.confidence = confidence
        self.model = None
        self.loaded = False
        self.inference_time = 0

    def load(self) -> bool:
        """Load model - auto-downloads if not present"""
        try:
            from ultralytics import YOLO
            logger.info(f"Loading model {self.model_name}...")
            self.model = YOLO(self.model_name)
            self.loaded = True

            if has_hailo():
                logger.info("✅ Hailo NPU detected - will export to .hef if not already done")
            else:
                logger.info("✅ Model loaded - running on CPU")

            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def detect(self, frame, classes: list = None) -> list:
        """
        Run inference on a single frame
        Returns: list of Detection objects
        """
        if not self.loaded or frame is None:
            return []

        try:
            t_start = time.time()

            kwargs = {"conf": self.confidence, "verbose": False}
            if classes:
                kwargs["classes"] = classes

            results = self.model(frame, **kwargs)
            self.inference_time = round((time.time() - t_start) * 1000, 1)

            detections = []
            for result in results:
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    class_name = result.names[class_id]
                    confidence = float(box.conf[0])
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]

                    detections.append(Detection(
                        class_name=class_name,
                        confidence=confidence,
                        box=[x1, y1, x2, y2]
                    ))

            return detections

        except Exception as e:
            logger.error(f"Error inference: {e}")
            return []

    def draw(self, frame, detections: list):
        """Draw bounding boxes on frame for preview"""
        for det in detections:
            x1, y1, x2, y2 = det.box
            label = f"{det.class_name} {det.confidence:.0%}"

            # Color per class
            color = (0, 255, 0)
            if det.class_name == "person":
                color = (255, 100, 0)
            elif "helmet" in det.class_name or "vest" in det.class_name:
                color = (0, 255, 100)
            elif "forklift" in det.class_name or "truck" in det.class_name:
                color = (0, 100, 255)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # Display inference time
        cv2.putText(frame, f"Inference: {self.inference_time}ms",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        return frame

    @staticmethod
    def filter_class(detections: list, class_name: str) -> list:
        return [d for d in detections if d.class_name == class_name]

    @staticmethod
    def count_class(detections: list, class_name: str) -> int:
        return len(YOLODetector.filter_class(detections, class_name))
