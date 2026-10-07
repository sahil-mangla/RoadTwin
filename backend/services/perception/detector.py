"""Detector abstraction over YOLOv8 so the pipeline is testable without weights.

`YoloDetector` imports ultralytics lazily: the API process never loads
torch, and tests run with `StubDetector` on machines without the weights.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from backend.core.config import settings


@dataclass(frozen=True)
class RawDetection:
    damage_type: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class DetectionResult:
    width: int
    height: int
    detections: list[RawDetection]


class Detector(Protocol):
    def detect(self, image_bytes: bytes) -> DetectionResult: ...


class StubDetector:
    """Returns canned detections; used by tests and weight-less dev runs."""

    def __init__(self, detections: list[RawDetection] | None = None):
        self._detections = detections or []

    def detect(self, image_bytes: bytes) -> DetectionResult:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
        return DetectionResult(width=width, height=height, detections=list(self._detections))


class YoloDetector:
    def __init__(self, weights_path: str):
        from ultralytics import YOLO  # lazy: heavy import, worker-only

        self._model = YOLO(weights_path)

    def detect(self, image_bytes: bytes) -> DetectionResult:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            width, height = img.size
            result = self._model.predict(
                img,
                conf=settings.yolo_conf_threshold,
                imgsz=settings.yolo_image_size,
                verbose=False,
            )[0]
        names = result.names
        detections = [
            RawDetection(
                damage_type=str(names[int(box.cls)]),
                confidence=float(box.conf),
                x1=float(box.xyxy[0][0]),
                y1=float(box.xyxy[0][1]),
                x2=float(box.xyxy[0][2]),
                y2=float(box.xyxy[0][3]),
            )
            for box in result.boxes
        ]
        return DetectionResult(width=width, height=height, detections=detections)


def load_detector() -> Detector:
    if not settings.yolo_weights_path:
        raise RuntimeError(
            "YOLO_WEIGHTS_PATH is not set -- point it at YOLOv8 weights trained on RDD2022"
        )
    return YoloDetector(settings.yolo_weights_path)
