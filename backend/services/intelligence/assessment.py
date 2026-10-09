"""Measures each segment's health, trend and forecast, and grades old forecasts.

Runs after observation scoring in the same job. Everything written here is
append-only: a RoadHealth row per measurement, a Prediction per horizon, a
ForecastEvaluation per graded forecast. Only the summary fields on
RoadSegment are overwritten (current_health_score, deterioration_rate,
current_risk_score, last_observed_at).
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.repository import (
    ForecastEvaluationRepository,
    PredictionRepository,
    RoadHealthRepository,
)
from backend.models.forecast_evaluation import ForecastEvaluation
from backend.models.prediction import Prediction
from backend.models.report import Report
from backend.models.road_health import RoadHealth
from backend.models.road_observation import RoadObservation
from backend.models.road_segment import RoadSegment
from backend.services.intelligence.deterioration import (
    check_history,
    deterioration_rate,
    trend_label,
)
from backend.services.intelligence.forecast import forecast_health
from backend.services.intelligence.health import Damage, compute_health

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssessmentSummary:
    segments_assessed: int
    health_records: int
    predictions: int
    forecasts_evaluated: int


async def assess_segments(session: AsyncSession, now: dt.datetime | None = None) -> AssessmentSummary:
    now = now or dt.datetime.now(dt.timezone.utc)

    rows = (
        await session.execute(
            sa.select(RoadObservation, Report.duplicate_of_id)
            .join(Report, Report.id == RoadObservation.report_id)
            .order_by(RoadObservation.recorded_at)
        )
    ).all()

    latest: dict[uuid.UUID, tuple[RoadObservation, bool]] = {}
    obs_reports: dict[uuid.UUID, set[uuid.UUID]] = {}
    last_seen: dict[uuid.UUID, dt.datetime] = {}
    for obs, duplicate_of in rows:
        obs_reports.setdefault(obs.road_segment_id, set()).add(obs.report_id)
        last_seen[obs.road_segment_id] = max(
            last_seen.get(obs.road_segment_id, obs.observed_at), obs.observed_at
        )
        key = obs.detection_id or obs.id
        latest[key] = (obs, duplicate_of is None)  # ascending recorded_at: newest wins

    damages: dict[uuid.UUID, list[Damage]] = {}
    for obs, is_canonical in latest.values():
        if is_canonical:  # near-duplicates describe damage already counted
            damages.setdefault(obs.road_segment_id, []).append(
                Damage(obs.severity, obs.verification_score or 0.0, obs.observed_at)
            )

    segments = (
        await session.execute(
            sa.select(RoadSegment).where(RoadSegment.id.in_(list(obs_reports) or [None]))
        )
    ).scalars().all()

    window_start = now - dt.timedelta(days=settings.history_window_days)
    history: dict[uuid.UUID, list[RoadHealth]] = {}
    for rec in (
        await session.execute(
            sa.select(RoadHealth)
            .where(RoadHealth.measured_at >= window_start)
            .order_by(RoadHealth.measured_at)
        )
    ).scalars():
        history.setdefault(rec.road_segment_id, []).append(rec)

    health_repo = RoadHealthRepository(session)
    prediction_repo = PredictionRepository(session)
    health_records = prediction_count = 0

    for segment in segments:
        result = compute_health(damages.get(segment.id, []), segment.length_meters, now, settings)
        past = history.get(segment.id, [])
        segment.current_health_score = result.score
        segment.last_observed_at = last_seen.get(segment.id)

        due = (
            not past
            or (now - past[-1].measured_at).total_seconds() / 3600 >= settings.health_snapshot_interval_hours
            or abs(result.score - past[-1].health_score) >= settings.health_resnapshot_delta
        )
        if not due:
            continue

        points = [(r.measured_at, r.health_score) for r in past] + [(now, result.score)]
        gate = check_history(points, len(obs_reports[segment.id]), settings)
        rate = risk = None
        forecasts = []
        if gate.sufficient:
            rate = deterioration_rate(points)
            forecasts = forecast_health(points, settings)
            risk = next(f.failure_probability for f in forecasts if f.horizon_days == 30)

        record = result.as_record()
        record["history_gate"] = {
            "sufficient": gate.sufficient,
            "reasons": gate.reasons,
            "points": gate.points,
            "span_days": round(gate.span_days, 2),
            "observation_reports": gate.observation_reports,
        }
        record["deterioration"] = (
            {"status": "ok", "rate_per_day": round(rate, 4), "trend": trend_label(rate, settings)}
            if rate is not None
            else {"status": "insufficient_data"}
        )

        await health_repo.create(
            road_segment_id=segment.id,
            measured_at=now,
            health_score=result.score,
            severity_burden=result.burdens["severity"],
            damage_density=result.burdens["density"],
            evidence_score=result.burdens["evidence"],
            deterioration_rate=rate,
            risk_score=risk,
            components=record,
        )
        health_records += 1
        for f in forecasts:
            await prediction_repo.create(
                road_segment_id=segment.id,
                generated_at=now,
                horizon_days=f.horizon_days,
                predicted_health_score=f.predicted_health_score,
                failure_probability=f.failure_probability,
                confidence=f.confidence,
                method=f.method,
                explanation=f.explanation,
            )
            prediction_count += 1
        segment.deterioration_rate = rate
        segment.current_risk_score = risk
        logger.info(
            "health segment=%s score=%.1f band=%s rate=%s forecasts=%d",
            segment.segment_identifier, result.score, result.band,
            "insufficient" if rate is None else f"{rate:.3f}/day", len(forecasts),
        )

    await session.flush()
    evaluated = await evaluate_forecasts(session, now)
    return AssessmentSummary(len(segments), health_records, prediction_count, evaluated)


async def evaluate_forecasts(session: AsyncSession, now: dt.datetime | None = None) -> int:
    """Grades forecasts whose target date (plus tolerance) has passed (FCST-03).

    Each prediction is graded once, against the RoadHealth measurement
    closest to its target date within the tolerance. A forecast with no
    measurement near its target stays ungraded rather than being compared
    with a distant reading.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    tolerance = dt.timedelta(days=settings.forecast_accuracy_tolerance_days)

    ungraded = (
        await session.execute(
            sa.select(Prediction)
            .outerjoin(ForecastEvaluation, ForecastEvaluation.prediction_id == Prediction.id)
            .where(ForecastEvaluation.id.is_(None))
        )
    ).scalars().all()
    due = [
        p for p in ungraded
        if p.generated_at + dt.timedelta(days=p.horizon_days) + tolerance <= now
    ]
    if not due:
        return 0

    by_segment: dict[uuid.UUID, list[RoadHealth]] = {}
    for rec in (
        await session.execute(
            sa.select(RoadHealth)
            .where(RoadHealth.road_segment_id.in_({p.road_segment_id for p in due}))
            .order_by(RoadHealth.measured_at)
        )
    ).scalars():
        by_segment.setdefault(rec.road_segment_id, []).append(rec)

    repo = ForecastEvaluationRepository(session)
    graded = 0
    for p in due:
        target = p.generated_at + dt.timedelta(days=p.horizon_days)
        near = [
            r for r in by_segment.get(p.road_segment_id, [])
            if abs(r.measured_at - target) <= tolerance
        ]
        if not near:
            continue
        actual = min(near, key=lambda r: abs(r.measured_at - target))
        error = p.predicted_health_score - actual.health_score
        await repo.create(
            prediction_id=p.id,
            road_segment_id=p.road_segment_id,
            road_health_id=actual.id,
            horizon_days=p.horizon_days,
            method=p.method,
            target_at=target,
            actual_measured_at=actual.measured_at,
            predicted_health_score=p.predicted_health_score,
            actual_health_score=actual.health_score,
            error=error,
            absolute_error=abs(error),
        )
        graded += 1
    await session.flush()
    return graded
