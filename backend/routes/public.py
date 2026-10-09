"""Public, read-only map API (PMAP-01, PMAP-02).

GET-only and unauthenticated, deliberately separate from `/api/authority`.
Nothing here exposes a device identity, an image, or staff-only fields
(priority explanations, repair notes).
"""

import datetime as dt
import uuid
from collections import Counter

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.session import get_session
from backend.models.detection import Detection
from backend.models.report import Report
from backend.models.road_health import RoadHealth
from backend.models.road_segment import RoadSegment
from backend.routes.health import segment_forecast
from backend.schemas.health import SegmentForecast
from backend.services.intelligence.deterioration import trend_label
from backend.services.intelligence.health import interpretation_band

router = APIRouter(prefix="/api/public", tags=["public"])

PROVISIONAL_NOTE = "Health scores and trends are provisional, tunable estimates, not validated measurements."


class PublicSegment(BaseModel):
    id: uuid.UUID
    segment_identifier: str
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    length_meters: float | None
    health_score: float | None
    band: str | None
    trend: str
    repair_status: str
    report_count: int
    last_observed_at: dt.datetime | None
    provisional: bool = True


class PublicReport(BaseModel):
    id: uuid.UUID
    latitude: float
    longitude: float
    observed_at: dt.datetime
    status: str
    segment_id: uuid.UUID | None
    damage_types: list[str]
    worst_severity: str | None
    is_duplicate: bool
    duplicate_count: int


class PublicMap(BaseModel):
    note: str
    segments: list[PublicSegment]
    reports: list[PublicReport]


class HealthPoint(BaseModel):
    measured_at: dt.datetime
    health_score: float
    band: str


class PublicSegmentDetail(BaseModel):
    segment: PublicSegment
    note: str
    health_history: list[HealthPoint]
    damage_composition: dict[str, int]
    outlook: SegmentForecast


_SEVERITY_ORDER = ["low", "moderate", "high", "critical"]


def _trend(rate: float | None) -> str:
    return "insufficient data" if rate is None else trend_label(rate, settings)


async def _segments(session: AsyncSession, only: uuid.UUID | None = None) -> list[PublicSegment]:
    counts = dict(
        (
            await session.execute(
                sa.select(Report.segment_id, sa.func.count())
                .where(Report.segment_id.is_not(None))
                .group_by(Report.segment_id)
            )
        ).all()
    )
    stmt = sa.select(RoadSegment).order_by(RoadSegment.segment_identifier)
    if only is not None:
        stmt = stmt.where(RoadSegment.id == only)
    return [
        PublicSegment(
            id=s.id, segment_identifier=s.segment_identifier,
            start_lat=s.start_lat, start_lng=s.start_lng, end_lat=s.end_lat, end_lng=s.end_lng,
            length_meters=s.length_meters, health_score=s.current_health_score,
            band=None if s.current_health_score is None else interpretation_band(s.current_health_score),
            trend=_trend(s.deterioration_rate), repair_status=s.repair_status,
            report_count=counts.get(s.id, 0), last_observed_at=s.last_observed_at,
        )
        for s in (await session.scalars(stmt)).all()
    ]


@router.get("/map", response_model=PublicMap)
async def public_map(limit: int = 2000, session: AsyncSession = Depends(get_session)) -> PublicMap:
    """Everything the public map draws: segments (health, trend) and damage reports."""
    reports = (
        await session.scalars(
            sa.select(Report)
            .where(Report.segment_id.is_not(None))
            .order_by(Report.timestamp.desc())
            .limit(max(1, min(limit, 5000)))
        )
    ).all()
    duplicates = Counter(r.duplicate_of_id for r in reports if r.duplicate_of_id)
    return PublicMap(
        note=PROVISIONAL_NOTE,
        segments=await _segments(session),
        reports=[
            PublicReport(
                id=r.id, latitude=r.latitude, longitude=r.longitude, observed_at=r.timestamp,
                status=r.status.value, segment_id=r.segment_id,
                damage_types=sorted({d.damage_type for d in r.detections}),
                worst_severity=max(
                    (d.severity for d in r.detections if d.severity in _SEVERITY_ORDER),
                    key=_SEVERITY_ORDER.index, default=None,
                ),
                is_duplicate=r.duplicate_of_id is not None,
                duplicate_count=duplicates.get(r.id, 0),
            )
            for r in reports
        ],
    )


@router.get("/segments/{segment_id}", response_model=PublicSegmentDetail)
async def public_segment(
    segment_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PublicSegmentDetail:
    segments = await _segments(session, only=segment_id)
    if not segments:
        raise HTTPException(status_code=404, detail="segment not found")
    history = (
        await session.scalars(
            sa.select(RoadHealth)
            .where(RoadHealth.road_segment_id == segment_id)
            .order_by(RoadHealth.measured_at)
        )
    ).all()
    composition = dict(
        (
            await session.execute(
                sa.select(Detection.damage_type, sa.func.count())
                .join(Report, Report.id == Detection.report_id)
                .where(Report.segment_id == segment_id, Report.duplicate_of_id.is_(None))
                .group_by(Detection.damage_type)
            )
        ).all()
    )
    return PublicSegmentDetail(
        segment=segments[0],
        note=PROVISIONAL_NOTE,
        health_history=[
            HealthPoint(measured_at=h.measured_at, health_score=h.health_score,
                        band=interpretation_band(h.health_score))
            for h in history
        ],
        damage_composition=composition,
        outlook=await segment_forecast(segment_id, session),
    )
