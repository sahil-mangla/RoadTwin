"""Walking-skeleton router proving Phase 1's schema is reachable end-to-end.

This router exists only to prove the seven-entity schema this phase locks
is real, reachable, and wired -- React (Plan 03) -> FastAPI -> the seven
repositories -> SQLAlchemy -> Alembic-migrated PostGIS, and back.

Beyond the original `POST/GET /reports` pair (Plan 02), this router adds
three more diagnostic endpoints (Plan 05):

- `POST /chain` seeds one linked row into all seven tables in a single
  call, proving SCHM-01 (seven distinct, *related* entities) end-to-end.
- `GET /schema-status` reports live per-entity row counts, so repeated
  seeding visibly grows the append-only tables (SCHM-02).
- `PATCH /reports/{report_id}/status` advances a report's status field, so
  the SCHM-03 lifecycle is observable, not just asserted in a test file.

It is **not** the citizen ingestion API -- that is INGT-01..04 in Phase 2
(image upload, EXIF GPS extraction, citizen identity, rate limiting). Every
endpoint in this file is scaffolding, mounted only when
`settings.skeleton_routes_enabled` is true (see `backend/main.py`). Once
Phase 2 lands the real ingestion endpoint, this router is removed or
demoted to a dev-only diagnostic (01-SKELETON.md "Skeleton Retirement
Criteria").
"""

import datetime as dt
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repository import (
    DetectionRepository,
    MaintenanceRecommendationRepository,
    PredictionRepository,
    ReportRepository,
    RoadHealthRepository,
    RoadObservationRepository,
    RoadSegmentRepository,
)
from backend.db.session import get_session
from backend.models.detection import Detection
from backend.models.maintenance_recommendation import MaintenanceRecommendation
from backend.models.prediction import Prediction
from backend.models.report import Report
from backend.models.road_health import RoadHealth
from backend.models.road_observation import RoadObservation
from backend.models.road_segment import RoadSegment
from backend.schemas.report import ReportCreate, ReportRead
from backend.schemas.skeleton import ChainSeedResult, ReportStatusUpdate, SchemaStatus

router = APIRouter(prefix="/api/skeleton", tags=["skeleton"])

# Fixed reporting order for /schema-status -- report first (as the
# original skeleton entity), then the chain's dependency order. The
# frontend renders rows in exactly this order rather than re-sorting
# client-side, so a missing entity shows up as a missing row.
_ENTITY_MODELS: list[tuple[str, type]] = [
    ("report", Report),
    ("detection", Detection),
    ("road_segment", RoadSegment),
    ("road_observation", RoadObservation),
    ("road_health", RoadHealth),
    ("prediction", Prediction),
    ("maintenance_recommendation", MaintenanceRecommendation),
]


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


@router.post("/chain", response_model=ChainSeedResult, status_code=status.HTTP_201_CREATED)
async def seed_chain(session: AsyncSession = Depends(get_session)) -> ChainSeedResult:
    """Seeds one linked row into all seven tables in a single call.

    Every entity is created through its repository -- the three
    append-only repositories (RoadObservation, RoadHealth, Prediction)
    offer no other creation path, which is exactly the point (SCHM-02,
    D-08). `get_session` commits once on clean exit, so the whole chain
    lands in a single transaction.
    """
    now = dt.datetime.now(dt.timezone.utc)
    # A short random suffix so repeated seeding never collides against
    # RoadSegment.segment_identifier's unique constraint.
    suffix = secrets.token_hex(4)

    segment = await RoadSegmentRepository(session).create(
        segment_identifier=f"SEG-SEED-{suffix}",
        start_lat=12.9716,
        start_lng=77.5946,
        end_lat=12.9726,
        end_lng=77.5956,
        road_name="Skeleton Chain-Seed Road",
        road_type="residential",
    )

    report = await ReportRepository(session).create(
        latitude=12.9716,
        longitude=77.5946,
        gps_accuracy_meters=6.0,
        timestamp=now,
        source="skeleton-seed",
        description="Chain-seed diagnostic report proving the 7-entity contract",
    )

    detection = await DetectionRepository(session).create(
        report_id=report.id,
        damage_type="pothole",
        confidence=0.82,
        bbox_x1=100.0,
        bbox_y1=150.0,
        bbox_x2=300.0,
        bbox_y2=340.0,
        bbox_area_ratio=0.18,
        severity="moderate",
    )

    observation = await RoadObservationRepository(session).create(
        road_segment_id=segment.id,
        report_id=report.id,
        detection_id=detection.id,
        observed_at=now,
        severity="moderate",
        damage_type="pothole",
        confidence=0.82,
    )

    health = await RoadHealthRepository(session).create(
        road_segment_id=segment.id,
        measured_at=now,
        health_score=72.5,
        severity_burden=0.4,
        damage_density=0.3,
    )

    prediction = await PredictionRepository(session).create(
        road_segment_id=segment.id,
        generated_at=now,
        horizon_days=30,
        predicted_health_score=68.0,
        method="ols",
    )

    recommendation = await MaintenanceRecommendationRepository(session).create(
        road_segment_id=segment.id,
        priority_score=55.0,
        urgency="medium",
        recommended_action="Schedule a pothole patch inspection",
        explanation=(
            "Seeded via the chain-seed diagnostic endpoint to prove the "
            "seven-entity contract is reachable end-to-end; not a real "
            "computed priority score."
        ),
    )

    return ChainSeedResult(
        report_id=report.id,
        detection_id=detection.id,
        road_segment_id=segment.id,
        road_observation_id=observation.id,
        road_health_id=health.id,
        prediction_id=prediction.id,
        maintenance_recommendation_id=recommendation.id,
        seeded_at=now,
    )


@router.get("/schema-status", response_model=SchemaStatus)
async def schema_status(session: AsyncSession = Depends(get_session)) -> SchemaStatus:
    """Live per-entity row counts, in the fixed `_ENTITY_MODELS` order.

    Every count is a `select(func.count())` construct against a mapped
    table -- no query text is ever assembled by string interpolation
    (threat T-01-03).
    """
    entities = []
    total = 0
    for name, model in _ENTITY_MODELS:
        count = await session.scalar(select(func.count()).select_from(model))
        count = count or 0
        entities.append({"entity": name, "count": count})
        total += count
    return SchemaStatus(entities=entities, total_rows=total)


@router.patch("/reports/{report_id}/status", response_model=ReportRead)
async def update_report_status(
    report_id: uuid.UUID,
    payload: ReportStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> ReportRead:
    """Advances a report's status field, making the SCHM-03 lifecycle observable.

    This endpoint does not enforce transition-validity rules (which prior
    state may move to which next state) -- that belongs to Phase 5's
    evidence fusion. Phase 1 only proves the field and its `unverified`
    default exist and are settable; real authenticated, role-gated status
    changes are AUTH-02 / RPWF-01 in Phase 7 (threat T-01-13).
    """
    repo = ReportRepository(session)
    report = await repo.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    report = await repo.update(report, status=payload.status)
    return ReportRead.model_validate(report)
