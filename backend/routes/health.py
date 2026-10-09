"""Read-only views of segment health, deterioration, forecasts and forecast accuracy.

Scores here are provisional, tunable baselines -- the responses say so.
"""

import math
import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.repository import RoadSegmentRepository
from backend.db.session import get_session
from backend.models.forecast_evaluation import ForecastEvaluation
from backend.models.prediction import Prediction
from backend.models.road_health import RoadHealth
from backend.models.road_observation import RoadObservation
from backend.schemas.health import (
    AccuracyRow,
    AccuracySummary,
    DeteriorationView,
    EvaluationRow,
    ForecastAccuracy,
    ForecastView,
    HealthHistory,
    HealthRecord,
    HistorySummary,
    HorizonView,
    SegmentForecast,
)
from backend.services.intelligence.deterioration import check_history, trend_label
from backend.services.intelligence.health import interpretation_band

router = APIRouter(prefix="/api", tags=["health"])


def _record(r: RoadHealth) -> HealthRecord:
    return HealthRecord(
        id=r.id,
        measured_at=r.measured_at,
        health_score=r.health_score,
        band=interpretation_band(r.health_score),
        deterioration_rate=r.deterioration_rate,
        risk_score=r.risk_score,
        components=r.components,
    )


async def _require_segment(session: AsyncSession, segment_id: uuid.UUID) -> None:
    if await RoadSegmentRepository(session).get(segment_id) is None:
        raise HTTPException(status_code=404, detail="segment not found")


async def _accuracy(session: AsyncSession, segment_id: uuid.UUID | None = None) -> AccuracySummary:
    stmt = sa.select(
        ForecastEvaluation.horizon_days,
        sa.func.count(),
        sa.func.avg(ForecastEvaluation.absolute_error),
        sa.func.avg(ForecastEvaluation.error),
        sa.func.avg(ForecastEvaluation.error * ForecastEvaluation.error),
    ).group_by(ForecastEvaluation.horizon_days).order_by(ForecastEvaluation.horizon_days)
    if segment_id is not None:
        stmt = stmt.where(ForecastEvaluation.road_segment_id == segment_id)
    return AccuracySummary(
        horizons=[
            AccuracyRow(
                horizon_days=h, evaluated=n, mean_absolute_error=float(mae),
                bias=float(bias), rmse=math.sqrt(float(mse)),
            )
            for h, n, mae, bias, mse in (await session.execute(stmt)).all()
        ]
    )


@router.get("/segments/{segment_id}/health", response_model=HealthHistory)
async def segment_health(
    segment_id: uuid.UUID, limit: int = 200, session: AsyncSession = Depends(get_session)
) -> HealthHistory:
    await _require_segment(session, segment_id)
    rows = (
        await session.scalars(
            sa.select(RoadHealth)
            .where(RoadHealth.road_segment_id == segment_id)
            .order_by(RoadHealth.measured_at.desc())
            .limit(max(1, min(limit, 1000)))
        )
    ).all()
    records = [_record(r) for r in reversed(rows)]
    return HealthHistory(current=records[-1] if records else None, history=records)


@router.get("/segments/{segment_id}/forecast", response_model=SegmentForecast)
async def segment_forecast(
    segment_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> SegmentForecast:
    await _require_segment(session, segment_id)
    history = (
        await session.scalars(
            sa.select(RoadHealth)
            .where(RoadHealth.road_segment_id == segment_id)
            .order_by(RoadHealth.measured_at)
        )
    ).all()
    obs_reports = await session.scalar(
        sa.select(sa.func.count(sa.distinct(RoadObservation.report_id))).where(
            RoadObservation.road_segment_id == segment_id
        )
    )
    points = [(r.measured_at, r.health_score) for r in history]
    gate = check_history(points, obs_reports or 0, settings)
    summary = HistorySummary(
        points=gate.points, span_days=round(gate.span_days, 2),
        observation_reports=gate.observation_reports,
    )
    latest = history[-1] if history else None

    if gate.sufficient and latest is not None and latest.deterioration_rate is not None:
        deterioration = DeteriorationView(
            status="ok",
            rate_per_day=latest.deterioration_rate,
            trend=trend_label(latest.deterioration_rate, settings),
            history=summary,
        )
    else:
        deterioration = DeteriorationView(
            status="insufficient_data", reasons=gate.reasons, history=summary
        )

    forecast = ForecastView(status="insufficient_data", reasons=gate.reasons)
    if gate.sufficient:
        newest = await session.scalar(
            sa.select(sa.func.max(Prediction.generated_at)).where(
                Prediction.road_segment_id == segment_id
            )
        )
        if newest is not None:
            preds = (
                await session.scalars(
                    sa.select(Prediction)
                    .where(Prediction.road_segment_id == segment_id, Prediction.generated_at == newest)
                    .order_by(Prediction.horizon_days)
                )
            ).all()
            forecast = ForecastView(
                status="ok",
                generated_at=newest,
                horizons=[
                    HorizonView(
                        horizon_days=p.horizon_days,
                        predicted_health_score=p.predicted_health_score,
                        predicted_band=interpretation_band(p.predicted_health_score),
                        failure_probability=p.failure_probability,
                        confidence=p.confidence,
                        method=p.method,
                        explanation=p.explanation,
                    )
                    for p in preds
                ],
            )

    return SegmentForecast(
        segment_id=segment_id,
        health_score=latest.health_score if latest else None,
        band=interpretation_band(latest.health_score) if latest else None,
        measured_at=latest.measured_at if latest else None,
        deterioration=deterioration,
        forecast=forecast,
        accuracy=await _accuracy(session, segment_id),
    )


@router.get("/forecast-accuracy", response_model=ForecastAccuracy)
async def forecast_accuracy(
    limit: int = 20, session: AsyncSession = Depends(get_session)
) -> ForecastAccuracy:
    recent = (
        await session.scalars(
            sa.select(ForecastEvaluation)
            .order_by(ForecastEvaluation.target_at.desc())
            .limit(max(1, min(limit, 200)))
        )
    ).all()
    return ForecastAccuracy(
        overall=await _accuracy(session),
        recent=[
            EvaluationRow(
                segment_id=e.road_segment_id, horizon_days=e.horizon_days, method=e.method,
                target_at=e.target_at, predicted_health_score=e.predicted_health_score,
                actual_health_score=e.actual_health_score, error=e.error,
            )
            for e in recent
        ],
    )
