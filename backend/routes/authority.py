"""Authority dashboard API (AUTH-02..06, RPWF-01, PRIO-02).

Every route depends on `require_staff`: reading the dashboard and changing
anything both need an authenticated authority-staff session. This surface
is separate from the public, read-only `/api/public` API (PMAP-02).
"""

import datetime as dt
import uuid
from collections import Counter

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.session import get_session
from backend.models.authority import RepairEvent, StaffUser
from backend.models.maintenance_recommendation import MaintenanceRecommendation
from backend.models.prediction import Prediction
from backend.models.report import Report
from backend.models.road_health import RoadHealth
from backend.models.road_observation import RoadObservation
from backend.models.road_segment import RoadSegment
from backend.routes.health import segment_forecast
from backend.schemas.health import SegmentForecast
from backend.services.authority.auth import require_staff
from backend.services.authority.repair import STATUS_LABELS, transition_repair_status
from backend.services.intelligence.deterioration import trend_label
from backend.services.intelligence.health import interpretation_band
from backend.services.maintenance.prioritize import latest_recommendations
from backend.services.perception.queue import enqueue_segmentation

router = APIRouter(prefix="/api/authority", tags=["authority"], dependencies=[Depends(require_staff)])

PROVISIONAL_NOTE = (
    "Priority and health scores are provisional, tunable estimates -- not validated "
    "engineering assessments. Weights and thresholds are configuration values."
)


class QueueItem(BaseModel):
    rank: int
    segment_id: uuid.UUID
    segment_identifier: str
    road_name: str | None
    priority_score: float
    urgency: str
    recommended_action: str
    explanation: str
    health_score: float | None
    band: str | None
    trend: str
    repair_status: str
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    generated_at: dt.datetime


class Overview(BaseModel):
    note: str
    segments: int
    assessed_segments: int
    average_health: float | None
    band_counts: dict[str, int]
    critical_roads: int
    rapidly_deteriorating: int
    predicted_failures: int
    repair_status_counts: dict[str, int]
    top_priorities: list[QueueItem]


def _trend(rate: float | None) -> str:
    return "insufficient data" if rate is None else trend_label(rate, settings)


async def _queue(session: AsyncSession) -> list[QueueItem]:
    recs = await latest_recommendations(session)
    segments = {
        s.id: s for s in (await session.scalars(sa.select(RoadSegment).where(RoadSegment.id.in_(list(recs) or [None])))).all()
    }
    ordered = sorted(recs.values(), key=lambda r: (-r.priority_score, str(r.road_segment_id)))
    items = []
    for rank, rec in enumerate(ordered, start=1):
        s = segments[rec.road_segment_id]
        items.append(
            QueueItem(
                rank=rank, segment_id=s.id, segment_identifier=s.segment_identifier,
                road_name=s.road_name, priority_score=rec.priority_score, urgency=rec.urgency,
                recommended_action=rec.recommended_action, explanation=rec.explanation,
                health_score=s.current_health_score,
                band=None if s.current_health_score is None else interpretation_band(s.current_health_score),
                trend=_trend(s.deterioration_rate), repair_status=s.repair_status,
                start_lat=s.start_lat, start_lng=s.start_lng, end_lat=s.end_lat, end_lng=s.end_lng,
                generated_at=rec.generated_at,
            )
        )
    return items


@router.get("/overview", response_model=Overview)
async def overview(session: AsyncSession = Depends(get_session)) -> Overview:
    segments = (await session.scalars(sa.select(RoadSegment))).all()
    scored = [s for s in segments if s.current_health_score is not None]
    bands = Counter(interpretation_band(s.current_health_score) for s in scored)

    newest = (
        sa.select(Prediction.road_segment_id, sa.func.max(Prediction.generated_at).label("at"))
        .group_by(Prediction.road_segment_id)
        .subquery()
    )
    failing = await session.scalar(
        sa.select(sa.func.count(sa.distinct(Prediction.road_segment_id)))
        .join(newest, sa.and_(
            Prediction.road_segment_id == newest.c.road_segment_id,
            Prediction.generated_at == newest.c.at,
        ))
        .where(sa.or_(
            Prediction.predicted_health_score < settings.forecast_failure_health_threshold,
            Prediction.failure_probability >= 0.5,
        ))
    )
    queue = await _queue(session)
    return Overview(
        note=PROVISIONAL_NOTE,
        segments=len(segments),
        assessed_segments=len(scored),
        average_health=(sum(s.current_health_score for s in scored) / len(scored)) if scored else None,
        band_counts={label: bands.get(label, 0) for label in ("Excellent", "Good", "Poor", "Critical", "Severely degraded")},
        critical_roads=bands.get("Critical", 0) + bands.get("Severely degraded", 0),
        rapidly_deteriorating=sum(
            1 for s in segments
            if s.deterioration_rate is not None and s.deterioration_rate <= settings.deterioration_rapid_per_day
        ),
        predicted_failures=failing or 0,
        repair_status_counts=dict(Counter(s.repair_status for s in segments)),
        top_priorities=queue[:5],
    )


@router.get("/queue", response_model=list[QueueItem])
async def priority_queue(
    limit: int = 100, urgency: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[QueueItem]:
    items = await _queue(session)
    if urgency:
        items = [i for i in items if i.urgency == urgency]
    return items[: max(1, min(limit, 1000))]


class PriorityView(BaseModel):
    priority_score: float
    urgency: str
    recommended_action: str
    explanation: str
    components: dict | None
    generated_at: dt.datetime


class EvidenceItem(BaseModel):
    report_id: uuid.UUID
    damage_type: str | None
    severity: str | None
    confidence: float | None
    verification_score: float | None
    observed_at: dt.datetime
    evidence_components: dict | None
    counts_toward_health: bool


class ReportSummary(BaseModel):
    id: uuid.UUID
    status: str
    observed_at: dt.datetime
    community_upvotes: int
    verification_score: float | None
    is_duplicate: bool


class RepairEventRead(BaseModel):
    from_status: str
    to_status: str
    note: str | None
    staff_email: str
    created_at: dt.datetime


class SegmentDetail(BaseModel):
    note: str
    segment_id: uuid.UUID
    segment_identifier: str
    road_name: str | None
    road_type: str | None
    length_meters: float | None
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    traffic_exposure: float | None
    near_vulnerable_location: bool | None
    repair_status: str
    last_repaired_at: dt.datetime | None
    health_history: list[dict]
    damage_composition: dict[str, dict[str, int]]
    evidence: list[EvidenceItem]
    reports: list[ReportSummary]
    outlook: SegmentForecast
    priority: PriorityView | None
    priority_history: list[dict]
    repair_events: list[RepairEventRead]


async def _segment_or_404(session: AsyncSession, segment_id: uuid.UUID) -> RoadSegment:
    segment = await session.get(RoadSegment, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="segment not found")
    return segment


@router.get("/segments/{segment_id}", response_model=SegmentDetail)
async def segment_detail(segment_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> SegmentDetail:
    s = await _segment_or_404(session, segment_id)

    health = (await session.scalars(
        sa.select(RoadHealth).where(RoadHealth.road_segment_id == segment_id).order_by(RoadHealth.measured_at)
    )).all()

    rows = (await session.execute(
        sa.select(RoadObservation, Report.duplicate_of_id)
        .join(Report, Report.id == RoadObservation.report_id)
        .where(RoadObservation.road_segment_id == segment_id)
        .order_by(RoadObservation.recorded_at)
    )).all()
    latest: dict = {}
    for obs, duplicate_of in rows:
        latest[obs.detection_id or obs.id] = (obs, duplicate_of)
    evidence, composition = [], {}
    for obs, duplicate_of in latest.values():
        counts = duplicate_of is None and (s.last_repaired_at is None or obs.observed_at > s.last_repaired_at)
        evidence.append(EvidenceItem(
            report_id=obs.report_id, damage_type=obs.damage_type, severity=obs.severity,
            confidence=obs.confidence, verification_score=obs.verification_score,
            observed_at=obs.observed_at, evidence_components=obs.evidence_components,
            counts_toward_health=counts,
        ))
        if counts:
            by_sev = composition.setdefault(obs.damage_type or "unknown", {})
            by_sev[obs.severity or "unknown"] = by_sev.get(obs.severity or "unknown", 0) + 1
    evidence.sort(key=lambda e: e.observed_at, reverse=True)

    reports = (await session.scalars(
        sa.select(Report).where(Report.segment_id == segment_id).order_by(Report.timestamp.desc())
    )).all()

    recs = (await session.scalars(
        sa.select(MaintenanceRecommendation)
        .where(MaintenanceRecommendation.road_segment_id == segment_id)
        .order_by(MaintenanceRecommendation.generated_at)
    )).all()
    events = (await session.execute(
        sa.select(RepairEvent, StaffUser.email)
        .join(StaffUser, StaffUser.id == RepairEvent.staff_user_id)
        .where(RepairEvent.road_segment_id == segment_id)
        .order_by(RepairEvent.created_at)
    )).all()

    latest_rec = recs[-1] if recs else None
    return SegmentDetail(
        note=PROVISIONAL_NOTE,
        segment_id=s.id, segment_identifier=s.segment_identifier, road_name=s.road_name,
        road_type=s.road_type, length_meters=s.length_meters,
        start_lat=s.start_lat, start_lng=s.start_lng, end_lat=s.end_lat, end_lng=s.end_lng,
        traffic_exposure=s.traffic_exposure, near_vulnerable_location=s.near_vulnerable_location,
        repair_status=s.repair_status, last_repaired_at=s.last_repaired_at,
        health_history=[
            {"measured_at": h.measured_at, "health_score": h.health_score,
             "band": interpretation_band(h.health_score), "burdens": (h.components or {}).get("burdens")}
            for h in health
        ],
        damage_composition=composition,
        evidence=evidence,
        reports=[
            ReportSummary(id=r.id, status=r.status.value, observed_at=r.timestamp,
                          community_upvotes=r.community_upvotes, verification_score=r.verification_score,
                          is_duplicate=r.duplicate_of_id is not None)
            for r in reports
        ],
        outlook=await segment_forecast(segment_id, session),
        priority=None if latest_rec is None else PriorityView(
            priority_score=latest_rec.priority_score, urgency=latest_rec.urgency,
            recommended_action=latest_rec.recommended_action, explanation=latest_rec.explanation,
            components=latest_rec.components, generated_at=latest_rec.generated_at,
        ),
        priority_history=[
            {"generated_at": r.generated_at, "priority_score": r.priority_score, "urgency": r.urgency}
            for r in recs
        ],
        repair_events=[
            RepairEventRead(from_status=e.from_status, to_status=e.to_status, note=e.note,
                            staff_email=email, created_at=e.created_at)
            for e, email in events
        ],
    )


class RepairStatusChange(BaseModel):
    status: str = Field(pattern="^(received|in_progress|resolved)$")
    note: str | None = Field(default=None, max_length=2000)


class RepairStatusResult(BaseModel):
    repair_status: str
    label: str
    citizens_notified: int


@router.post("/segments/{segment_id}/repair-status", response_model=RepairStatusResult)
async def change_repair_status(
    segment_id: uuid.UUID,
    body: RepairStatusChange,
    session: AsyncSession = Depends(get_session),
    staff: StaffUser = Depends(require_staff),
) -> RepairStatusResult:
    segment = await _segment_or_404(session, segment_id)
    _, notified = await transition_repair_status(session, segment, body.status, staff, body.note)
    await enqueue_segmentation()  # re-assess health/priority, e.g. after a repair
    return RepairStatusResult(
        repair_status=segment.repair_status, label=STATUS_LABELS[segment.repair_status],
        citizens_notified=notified,
    )


class EnhancementInputs(BaseModel):
    """Optional external inputs. Send only the fields to change; null clears one."""

    road_name: str | None = Field(default=None, max_length=200)
    road_type: str | None = Field(default=None, max_length=64)
    traffic_exposure: float | None = Field(default=None, ge=0, le=1)
    near_vulnerable_location: bool | None = None


@router.patch("/segments/{segment_id}/inputs", response_model=SegmentDetail)
async def update_inputs(
    segment_id: uuid.UUID, body: EnhancementInputs, session: AsyncSession = Depends(get_session)
) -> SegmentDetail:
    segment = await _segment_or_404(session, segment_id)
    for field in body.model_fields_set:
        setattr(segment, field, getattr(body, field))
    await session.flush()
    await enqueue_segmentation()
    return await segment_detail(segment_id, session)
