"""Ranks every assessed segment into the maintenance queue (PRIO-01, PRIO-02).

Runs after health assessment. Appends a MaintenanceRecommendation when a
segment has none yet, or its score moved by `priority_resnapshot_delta`, or
its urgency changed -- so the queue history shows how priorities evolved.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import Counter
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.repository import MaintenanceRecommendationRepository
from backend.models.maintenance_recommendation import MaintenanceRecommendation
from backend.models.report import Report
from backend.models.road_health import RoadHealth
from backend.models.road_observation import RoadObservation
from backend.models.road_segment import RoadSegment
from backend.services.maintenance.priority import PriorityInputs, compute_priority


@dataclass(frozen=True)
class PrioritySummary:
    segments_ranked: int
    recommendations: int


async def latest_recommendations(
    session: AsyncSession,
) -> dict[uuid.UUID, MaintenanceRecommendation]:
    newest = (
        sa.select(
            MaintenanceRecommendation.road_segment_id,
            sa.func.max(MaintenanceRecommendation.generated_at).label("at"),
        )
        .group_by(MaintenanceRecommendation.road_segment_id)
        .subquery()
    )
    rows = (
        await session.scalars(
            sa.select(MaintenanceRecommendation).join(
                newest,
                sa.and_(
                    MaintenanceRecommendation.road_segment_id == newest.c.road_segment_id,
                    MaintenanceRecommendation.generated_at == newest.c.at,
                ),
            )
        )
    ).all()
    return {r.road_segment_id: r for r in rows}


async def dominant_damage_types(session: AsyncSession) -> dict[uuid.UUID, str]:
    """Most common damage type among each segment's current (post-repair) canonical damage."""
    rows = (
        await session.execute(
            sa.select(
                RoadObservation.road_segment_id,
                RoadObservation.detection_id,
                RoadObservation.damage_type,
                RoadObservation.observed_at,
                RoadSegment.last_repaired_at,
            )
            .join(Report, Report.id == RoadObservation.report_id)
            .join(RoadSegment, RoadSegment.id == RoadObservation.road_segment_id)
            .where(Report.duplicate_of_id.is_(None))
        )
    ).all()
    seen: dict[uuid.UUID, dict] = {}
    for seg_id, det_id, damage_type, observed_at, repaired_at in rows:
        if damage_type and (repaired_at is None or observed_at > repaired_at):
            seen.setdefault(seg_id, {})[det_id] = damage_type
    return {
        seg_id: Counter(types.values()).most_common(1)[0][0]
        for seg_id, types in seen.items()
    }


async def prioritize_segments(session: AsyncSession, now: dt.datetime | None = None) -> PrioritySummary:
    now = now or dt.datetime.now(dt.timezone.utc)
    newest_health = (
        sa.select(RoadHealth.road_segment_id, sa.func.max(RoadHealth.measured_at).label("at"))
        .group_by(RoadHealth.road_segment_id)
        .subquery()
    )
    pairs = (
        await session.execute(
            sa.select(RoadSegment, RoadHealth)
            .join(RoadHealth, RoadHealth.road_segment_id == RoadSegment.id)
            .join(
                newest_health,
                sa.and_(
                    RoadHealth.road_segment_id == newest_health.c.road_segment_id,
                    RoadHealth.measured_at == newest_health.c.at,
                ),
            )
        )
    ).all()
    previous = await latest_recommendations(session)
    damage_types = await dominant_damage_types(session)
    repo = MaintenanceRecommendationRepository(session)
    written = 0

    for segment, health in pairs:
        result = compute_priority(
            PriorityInputs(
                severity_burden=health.severity_burden,
                deterioration_rate=segment.deterioration_rate,
                density_burden=health.damage_density,
                evidence_burden=health.evidence_score,
                health_score=segment.current_health_score,
                traffic_exposure=segment.traffic_exposure,
                road_type=segment.road_type,
                near_vulnerable_location=segment.near_vulnerable_location,
                last_repaired_at=segment.last_repaired_at,
                dominant_damage_type=damage_types.get(segment.id),
            ),
            now,
            settings,
        )
        prior = previous.get(segment.id)
        if (
            prior is not None
            and prior.urgency == result.urgency
            and abs(prior.priority_score - result.score) < settings.priority_resnapshot_delta
        ):
            continue
        await repo.create(
            road_segment_id=segment.id,
            priority_score=result.score,
            urgency=result.urgency,
            recommended_action=result.recommended_action,
            explanation=result.explanation,
            components=result.as_record(),
            generated_at=now,
        )
        written += 1
    await session.flush()
    return PrioritySummary(len(pairs), written)
