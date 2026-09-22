"""Re-exports Base + models so Alembic's `target_metadata` sees the full schema."""

from .base import Base
from .detection import Detection
from .maintenance_recommendation import MaintenanceRecommendation
from .prediction import Prediction
from .report import Report
from .road_health import RoadHealth
from .road_observation import RoadObservation
from .road_segment import RoadSegment

__all__ = [
    "Base",
    "Report",
    "Detection",
    "RoadSegment",
    "RoadObservation",
    "RoadHealth",
    "Prediction",
    "MaintenanceRecommendation",
]
