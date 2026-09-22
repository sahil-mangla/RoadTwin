"""Walking-skeleton router proving Phase 1's schema is reachable end-to-end.

This router exists only to prove the seven-entity schema this phase locks
is real, reachable, and wired -- React (Plan 03) -> FastAPI -> the
`ReportRepository` -> SQLAlchemy -> Alembic-migrated PostGIS, and back.

It is **not** the citizen ingestion API -- that is INGT-01..04 in Phase 2
(image upload, EXIF GPS extraction, citizen identity, rate limiting). Once
Phase 2 lands the real ingestion endpoint, this router is removed or
demoted to a dev-only diagnostic (01-SKELETON.md "Skeleton Retirement
Criteria").
"""

import datetime as dt

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repository import ReportRepository
from backend.db.session import get_session
from backend.schemas.report import ReportCreate, ReportRead

router = APIRouter(prefix="/api/skeleton", tags=["skeleton"])


@router.post("/reports", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate, session: AsyncSession = Depends(get_session)
) -> ReportRead:
    # `status` is never accepted from the request body -- ReportCreate has
    # no such field, so arrival status is always the Report model's
    # `unverified` default (SCHM-03: arrival status is a system decision,
    # not a client claim; threat T-01-08).
    fields = payload.model_dump()
    if fields.get("timestamp") is None:
        fields["timestamp"] = dt.datetime.now(dt.timezone.utc)

    report = await ReportRepository(session).create(**fields)
    return ReportRead.model_validate(report)


@router.get("/reports", response_model=list[ReportRead])
async def list_reports(session: AsyncSession = Depends(get_session)) -> list[ReportRead]:
    reports = await ReportRepository(session).list(
        limit=50, order_by="created_at", descending=True
    )
    return [ReportRead.model_validate(r) for r in reports]
