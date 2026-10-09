"""Read-only view of aggregated road segments (SPAT-02)."""

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repository import RoadSegmentRepository
from backend.db.session import get_session
from backend.models.report import Report
from backend.schemas.entities import RoadSegmentRead

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
