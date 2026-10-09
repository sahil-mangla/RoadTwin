"""Pydantic v2 contracts for the six entities beyond Report.

The ASVS V5 input-validation control point for each entity: every
`*Create` model carries the numeric/string bounds that make the contract
self-defending, and every `*Read` model mirrors its ORM model via
`from_attributes=True`.

`status` is deliberately absent from `DetectionCreate` -- arrival status is
a system decision (defaulting to `unverified`), never a client claim
(SCHM-03, mirrors `ReportCreate`'s same omission).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DetectionCreate(BaseModel):
    report_id: uuid.UUID
    damage_type: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0, le=1)
    bbox_x1: float = Field(ge=0)
    bbox_y1: float = Field(ge=0)
    bbox_x2: float = Field(ge=0)
    bbox_y2: float = Field(ge=0)
    bbox_area_ratio: float = Field(ge=0, le=1)
    severity: str | None = None


class DetectionRead(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    damage_type: str
    confidence: float
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    bbox_area_ratio: float
    severity: str | None
    status: str

    model_config = ConfigDict(from_attributes=True)


class RoadSegmentCreate(BaseModel):
    segment_identifier: str = Field(min_length=1, max_length=128)
    start_lat: float = Field(ge=-90, le=90)
    start_lng: float = Field(ge=-180, le=180)
    end_lat: float = Field(ge=-90, le=90)
    end_lng: float = Field(ge=-180, le=180)
    road_name: str | None = None
    road_type: str | None = None
    length_meters: float | None = Field(default=None, ge=0)


class RoadSegmentRead(BaseModel):
    id: uuid.UUID
    segment_identifier: str
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    road_name: str | None
    road_type: str | None
    length_meters: float | None
    current_health_score: float | None
    current_risk_score: float | None
    deterioration_rate: float | None
    last_observed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class RoadObservationCreate(BaseModel):
    road_segment_id: uuid.UUID
    report_id: uuid.UUID
    detection_id: uuid.UUID | None = None
    observed_at: datetime
    severity: str | None = None
    damage_type: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification_score: float | None = Field(default=None, ge=0, le=1)
    contribution_weight: float | None = Field(default=None, ge=0, le=1)


class RoadObservationRead(BaseModel):
    id: uuid.UUID
    road_segment_id: uuid.UUID
    report_id: uuid.UUID
    detection_id: uuid.UUID | None
    observed_at: datetime
    severity: str | None
    damage_type: str | None
    confidence: float | None
    verification_score: float | None
    contribution_weight: float | None
    evidence_components: dict | None = None
    recorded_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class RoadHealthCreate(BaseModel):
    road_segment_id: uuid.UUID
    measured_at: datetime
    health_score: float = Field(ge=0, le=100)
    severity_burden: float | None = None
    damage_density: float | None = None
    evidence_score: float | None = None
    deterioration_rate: float | None = None
    risk_score: float | None = None


class RoadHealthRead(BaseModel):
    id: uuid.UUID
    road_segment_id: uuid.UUID
    measured_at: datetime
    health_score: float
    severity_burden: float | None
    damage_density: float | None
    evidence_score: float | None
    deterioration_rate: float | None
    risk_score: float | None

    model_config = ConfigDict(from_attributes=True)


class PredictionCreate(BaseModel):
    road_segment_id: uuid.UUID
    generated_at: datetime
    horizon_days: int = Field(gt=0)
    predicted_health_score: float = Field(ge=0, le=100)
    failure_probability: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = None
    method: str = Field(min_length=1, max_length=64)


class PredictionRead(BaseModel):
    id: uuid.UUID
    road_segment_id: uuid.UUID
    generated_at: datetime
    horizon_days: int
    predicted_health_score: float
    failure_probability: float | None
    confidence: float | None
    method: str

    model_config = ConfigDict(from_attributes=True)


class MaintenanceRecommendationCreate(BaseModel):
    road_segment_id: uuid.UUID
    priority_score: float = Field(ge=0)
    urgency: str = Field(min_length=1, max_length=32)
    recommended_action: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class MaintenanceRecommendationRead(BaseModel):
    id: uuid.UUID
    road_segment_id: uuid.UUID
    priority_score: float
    urgency: str
    recommended_action: str
    generated_at: datetime
    explanation: str

    model_config = ConfigDict(from_attributes=True)
