"""Pydantic v2 contracts for Report -- the ASVS V5 input-validation control point."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import ReportStatus


class ReportCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    gps_accuracy_meters: float | None = Field(default=None, ge=0)
    timestamp: datetime | None = None
    source: str = "citizen"
    description: str | None = Field(default=None, max_length=2000)
    image_path: str | None = None


class ReportRead(BaseModel):
    id: uuid.UUID
    latitude: float
    longitude: float
    gps_accuracy_meters: float | None
    timestamp: datetime
    source: str
    description: str | None
    status: ReportStatus
    community_upvotes: int
    verification_score: float | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
