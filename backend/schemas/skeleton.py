"""Pydantic v2 contracts for the skeleton router's diagnostic endpoints.

`ChainSeedResult`, `SchemaStatus`, `EntityCount` and `ReportStatusUpdate`
back the chain-seed / schema-status / status-transition endpoints defined
in `backend/routes/skeleton.py` -- scaffolding that proves the seven-entity
contract is reachable, not production API surface. See that module's
docstring for the retirement criteria (`01-SKELETON.md`).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from backend.models.enums import ReportStatus


class EntityCount(BaseModel):
    entity: str
    count: int


class SchemaStatus(BaseModel):
    entities: list[EntityCount]
    total_rows: int


class ChainSeedResult(BaseModel):
    report_id: uuid.UUID
    detection_id: uuid.UUID
    road_segment_id: uuid.UUID
    road_observation_id: uuid.UUID
    road_health_id: uuid.UUID
    prediction_id: uuid.UUID
    maintenance_recommendation_id: uuid.UUID
    seeded_at: datetime


class ReportStatusUpdate(BaseModel):
    status: ReportStatus
