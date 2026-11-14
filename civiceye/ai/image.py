"""Replaceable image-inference interface, independent of the web routes.

Phase 1 ships NO trained pothole/litter weights. The default detector therefore
reports an honest "unavailable" state. It never fabricates predictions. A real
YOLO-family backend will plug in behind the same interface in a later phase.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Detection:
    model_label: str
    category: str | None  # mapped application category (explicit config), may be None
    confidence: float
    box_xyxy: tuple[float, float, float, float]


@dataclass
class ImageInferenceResult:
    status: str  # ok | unavailable | error
    method: str
    model_id: str | None
    detections: list[Detection] = field(default_factory=list)
    message: str = ""
    inferred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class ImageDetector:
    """Interface. Implementations must not raise for bad model state; return status='error'."""
    method = "base"
    model_id: str | None = None

    @property
    def available(self) -> bool:
        return False

    def supported_categories(self) -> set[str]:
        return set()

    def predict(self, image_path: Path) -> ImageInferenceResult:  # pragma: no cover - interface
        raise NotImplementedError


class UnavailableDetector(ImageDetector):
    method = "unavailable"

    def __init__(self, reason: str):
        self.reason = reason

    def predict(self, image_path: Path) -> ImageInferenceResult:
        return ImageInferenceResult(status="unavailable", method=self.method, model_id=None, message=self.reason)


def get_image_detector(config) -> ImageDetector:
    weights = (config.get("IMAGE_MODEL_WEIGHTS") or "").strip()
    if not weights:
        return UnavailableDetector("No trained pothole/litter model is installed. Please choose the category manually.")
    if not Path(weights).is_file():
        return UnavailableDetector("Configured model weights were not found. Please choose the category manually.")
    # A real backend (PyTorch + YOLO-family model) is planned for phase 2.
    return UnavailableDetector("Image model backend is not implemented in this build. Please choose manually.")
