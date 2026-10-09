"""Read-only view of aggregated road segments (SPAT-02)."""

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repository import RoadSegmentRepository
from backend.db.session import get_session
from backend.models.report import Report
from backend.models.road_observation import RoadObservation
from backend.schemas.entities import RoadObservationRead, RoadSegmentRead

router = APIRouter(prefix="/api/segments", tags=["segments"])


class SegmentSummary(RoadSegmentRead):
    report_count: int
    canonical_report_count: int


class SegmentDetail(SegmentSummary):
    report_ids: list[uuid.UUID]


async def _counts(session: AsyncSession, segment_ids: list[uuid.UUID] | None = None):
    stmt = sa.select(
        Report.segment_id,
        sa.func.count(),
        sa.func.count().filter(Report.duplicate_of_id.is_(None)),
    ).where(Report.segment_id.is_not(None)).group_by(Report.segment_id)
    if segment_ids is not None:
        stmt = stmt.where(Report.segment_id.in_(segment_ids))
    return {sid: (total, canon) for sid, total, canon in (await session.execute(stmt)).all()}


@router.get("", response_model=list[SegmentSummary])
async def list_segments(
    limit: int = 100, session: AsyncSession = Depends(get_session)
) -> list[SegmentSummary]:
    limit = max(1, min(limit, 500))
    segments = await RoadSegmentRepository(session).list(limit=limit, order_by="segment_identifier")
    counts = await _counts(session, [s.id for s in segments])
    return [
        SegmentSummary(
            **RoadSegmentRead.model_validate(s).model_dump(),
            report_count=counts.get(s.id, (0, 0))[0],
            canonical_report_count=counts.get(s.id, (0, 0))[1],
        )
        for s in segments
    ]


@router.get("/{segment_id}", response_model=SegmentDetail)
async def get_segment(
    segment_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SegmentDetail:
    segment = await RoadSegmentRepository(session).get(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="segment not found")
    report_ids = list(
        (await session.scalars(sa.select(Report.id).where(Report.segment_id == segment_id))).all()
    )
    total, canon = (await _counts(session, [segment_id])).get(segment_id, (0, 0))
    return SegmentDetail(
        **RoadSegmentRead.model_validate(segment).model_dump(),
        report_count=total,
        canonical_report_count=canon,
        report_ids=report_ids,
    )


@router.get("/{segment_id}/observations", response_model=list[RoadObservationRead])
async def segment_observation_history(
    segment_id: uuid.UUID,
    latest_only: bool = False,
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
) -> list[RoadObservationRead]:
    """The segment's longitudinal history (HLTH-01), oldest damage first.

    Each detection can have several snapshots as its evidence grew;
    `latest_only` keeps just the newest snapshot of each.
    """
    if await RoadSegmentRepository(session).get(segment_id) is None:
        raise HTTPException(status_code=404, detail="segment not found")
    stmt = (
        sa.select(RoadObservation)
        .where(RoadObservation.road_segment_id == segment_id)
        .order_by(RoadObservation.observed_at, RoadObservation.recorded_at)
    )
    rows = list((await session.scalars(stmt)).all())
    if latest_only:
        newest = {}
        for row in rows:
            key = row.detection_id or row.id
            if key not in newest or row.recorded_at >= newest[key].recorded_at:
                newest[key] = row
        rows = sorted(newest.values(), key=lambda o: (o.observed_at, o.recorded_at))
    return [RoadObservationRead.model_validate(o) for o in rows[: max(1, min(limit, 1000))]]
