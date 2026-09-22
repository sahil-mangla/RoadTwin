from .entities import (
    DetectionCreate,
    DetectionRead,
    MaintenanceRecommendationCreate,
    MaintenanceRecommendationRead,
    PredictionCreate,
    PredictionRead,
    RoadHealthCreate,
    RoadHealthRead,
    RoadObservationCreate,
    RoadObservationRead,
    RoadSegmentCreate,
    RoadSegmentRead,
)
from .report import ReportCreate, ReportRead

__all__ = [
    "ReportCreate",
    "ReportRead",
    "DetectionCreate",
    "DetectionRead",
    "RoadSegmentCreate",
    "RoadSegmentRead",
    "RoadObservationCreate",
    "RoadObservationRead",
    "RoadHealthCreate",
    "RoadHealthRead",
    "PredictionCreate",
    "PredictionRead",
    "MaintenanceRecommendationCreate",
    "MaintenanceRecommendationRead",
]
