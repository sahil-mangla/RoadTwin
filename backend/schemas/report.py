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
    # D-08 / 01-REVIEW.md WR-02: defense in depth. The citizen route never
    # passes a client value here -- the object key is always server
    # generated (backend/services/ingestion/upload.py generate_object_key)
    # -- but constraining the pattern closes the unvalidated-`str` finding
    # even if a future caller tried to supply one directly.
    image_path: str | None = Field(
        default=None,
        max_length=256,
        pattern=r"^reports/[0-9a-fA-F-]{36}\.(jpg|png)$",
    )


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


class ReportImageUrl(BaseModel):
    """A freshly minted presigned image URL (D-09) -- never persisted or cached."""

    url: str
    expires_in_seconds: int


class ExifGpsCandidate(BaseModel):
    """A candidate pin position extracted from a photo's EXIF GPS tags.

    `source` is always the literal `"exif"` when coordinates were found so
    the frontend can label where an unconfirmed candidate pin came from --
    it is never treated as a submitted location (D-10, Phase 2 Plan 06).
    """

    latitude: float | None
    longitude: float | None
    source: str
