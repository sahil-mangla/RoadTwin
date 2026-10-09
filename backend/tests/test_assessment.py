"""HLTH-02..04, FCST-01..03 end to end, with a controllable clock."""

import datetime as dt

import pytest
import sqlalchemy as sa

from backend.db.repository import (
    DetectionRepository,
    ReportRepository,
    RoadObservationRepository,
    RoadSegmentRepository,
)
from backend.models.forecast_evaluation import ForecastEvaluation
from backend.models.prediction import Prediction
from backend.models.road_health import RoadHealth
from backend.services.intelligence.assessment import assess_segments, evaluate_forecasts

T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def day(n):
    return T0 + dt.timedelta(days=n)


async def make_segment(session):
    return await RoadSegmentRepository(session).create(
        segment_identifier="SEG-TEST", start_lat=13.0, start_lng=77.6,
        end_lat=13.001, end_lng=77.6, length_meters=110.0,
    )


async def add_damage(session, segment, when, severity="high", evidence=0.9, tag="r"):
    report = await ReportRepository(session).create(
        latitude=13.0, longitude=77.6, timestamp=when, perception_status="done",
        submitter_identity_key=f"{tag}-{when.isoformat()}", segment_id=segment.id,
    )
    detection = await DetectionRepository(session).create(
        report_id=report.id, damage_type="D40", confidence=0.9,
        bbox_x1=0, bbox_y1=0, bbox_x2=1, bbox_y2=1, bbox_area_ratio=0.1, severity=severity,
    )
    await RoadObservationRepository(session).create(
        road_segment_id=segment.id, report_id=report.id, detection_id=detection.id,
        observed_at=when, severity=severity, damage_type="D40", confidence=0.9,
        verification_score=evidence, recorded_at=when,
    )


async def health_rows(session, segment):
    return (
        await session.scalars(
            sa.select(RoadHealth).where(RoadHealth.road_segment_id == segment.id)
            .order_by(RoadHealth.measured_at)
        )
    ).all()


async def deteriorating_segment(session, days=(0, 5, 10, 15, 20)):
    """A segment that picks up a new serious defect at each step."""
    segment = await make_segment(session)
    for d in days:
        await add_damage(session, segment, day(d))
        await assess_segments(session, now=day(d))
    return segment


@pytest.mark.postgis
async def test_first_assessment_records_health_but_withholds_trend_and_forecast(session):
    segment = await make_segment(session)
    await add_damage(session, segment, day(0))
    summary = await assess_segments(session, now=day(0))

    (record,) = await health_rows(session, segment)
    assert summary.health_records == 1 and summary.predictions == 0
    assert 0 < record.health_score < 100
    assert segment.current_health_score == record.health_score
    assert record.deterioration_rate is None and segment.deterioration_rate is None
    assert record.components["band"] in {"Excellent", "Good", "Poor", "Critical", "Severely degraded"}
    assert record.components["history_gate"]["sufficient"] is False
    assert record.components["deterioration"]["status"] == "insufficient_data"
    assert set(record.components["burdens"]) == {"severity", "density", "temporal", "evidence"}


@pytest.mark.postgis
async def test_unchanged_health_within_a_day_adds_no_row(session):
    segment = await make_segment(session)
    await add_damage(session, segment, day(0))
    await assess_segments(session, now=day(0))
    again = await assess_segments(session, now=day(0) + dt.timedelta(hours=3))
    assert again.health_records == 0
    assert len(await health_rows(session, segment)) == 1


@pytest.mark.postgis
async def test_a_stable_road_still_builds_history_daily(session):
    segment = await make_segment(session)
    await add_damage(session, segment, day(-200))
    for d in (0, 1, 2):
        await assess_segments(session, now=day(d))
    assert len(await health_rows(session, segment)) == 3


@pytest.mark.postgis
async def test_gate_blocks_rate_and_forecast_until_history_is_sufficient(session):
    segment = await deteriorating_segment(session, days=(0, 5, 10))  # 3 points, 10 days
    rows = await health_rows(session, segment)
    assert all(r.deterioration_rate is None for r in rows)
    assert (await session.scalar(sa.select(sa.func.count()).select_from(Prediction))) == 0


@pytest.mark.postgis
async def test_sufficient_history_yields_negative_rate_and_three_horizons(session):
    segment = await deteriorating_segment(session, days=(0, 5, 10, 15))  # 4 points, 15 days
    latest = (await health_rows(session, segment))[-1]
    assert latest.deterioration_rate < 0
    assert segment.deterioration_rate == latest.deterioration_rate
    assert latest.risk_score is not None and segment.current_risk_score == latest.risk_score
    preds = (await session.scalars(sa.select(Prediction).order_by(Prediction.horizon_days))).all()
    assert [p.horizon_days for p in preds] == [30, 60, 90]
    assert {p.method for p in preds} == {"linear-ols-v1"}
    assert all(0 <= p.predicted_health_score <= 100 and p.explanation for p in preds)


@pytest.mark.postgis
async def test_five_or_more_points_switch_to_the_smoothing_method(session):
    await deteriorating_segment(session, days=(0, 5, 10, 15, 20))
    methods = {p.method for p in (await session.scalars(sa.select(Prediction))).all()}
    assert methods == {"linear-ols-v1", "holt-damped-v1"}  # 4th point linear, 5th Holt


@pytest.mark.postgis
async def test_predictions_are_append_only_across_runs(session):
    segment = await deteriorating_segment(session, days=(0, 5, 10, 15))
    first = {p.id: p.predicted_health_score for p in (await session.scalars(sa.select(Prediction))).all()}
    await add_damage(session, segment, day(20))
    await assess_segments(session, now=day(20))
    after = {p.id: p.predicted_health_score for p in (await session.scalars(sa.select(Prediction))).all()}
    assert len(after) == 2 * len(first)
    assert all(after[i] == v for i, v in first.items())  # old forecasts untouched


@pytest.mark.postgis
async def test_forecasts_are_graded_against_later_actuals(session):
    segment = await deteriorating_segment(session, days=(0, 5, 10, 15))
    # Keep measuring: a reading close to day 15 + 30 = 45.
    await assess_segments(session, now=day(45))
    # 30-day forecast target is day 45; tolerance 7 -> gradable from day 52.
    assert await evaluate_forecasts(session, now=day(50)) == 0
    graded = await evaluate_forecasts(session, now=day(53))
    assert graded >= 1

    evaluation = (
        await session.scalars(
            sa.select(ForecastEvaluation).where(ForecastEvaluation.horizon_days == 30)
        )
    ).first()
    assert evaluation.error == pytest.approx(
        evaluation.predicted_health_score - evaluation.actual_health_score
    )
    assert evaluation.absolute_error == abs(evaluation.error)
    assert evaluation.target_at == day(15) + dt.timedelta(days=30)

    assert await evaluate_forecasts(session, now=day(54)) == 0  # graded once only


@pytest.mark.postgis
async def test_forecast_with_no_measurement_near_its_target_stays_ungraded(session):
    await deteriorating_segment(session, days=(0, 5, 10, 15))
    assert await evaluate_forecasts(session, now=day(200)) == 0


@pytest.mark.postgis
async def test_forecast_endpoint_withholds_with_reasons_then_serves_numbers(client, session):
    segment = await make_segment(session)
    await add_damage(session, segment, day(0))
    await assess_segments(session, now=day(0))

    early = (await client.get(f"/api/segments/{segment.id}/forecast")).json()
    assert early["provisional"] is True
    assert early["deterioration"]["status"] == "insufficient_data"
    assert early["deterioration"]["rate_per_day"] is None
    assert early["forecast"]["status"] == "insufficient_data"
    assert early["forecast"]["horizons"] == [] and early["forecast"]["reasons"]
    assert early["band"] is not None

    for d in (5, 10, 15):
        await add_damage(session, segment, day(d))
        await assess_segments(session, now=day(d))
    later = (await client.get(f"/api/segments/{segment.id}/forecast")).json()
    assert later["deterioration"]["status"] == "ok"
    assert later["deterioration"]["trend"] in {"rapidly deteriorating", "deteriorating"}
    assert [h["horizon_days"] for h in later["forecast"]["horizons"]] == [30, 60, 90]
    assert all(h["explanation"] and h["predicted_band"] for h in later["forecast"]["horizons"])


@pytest.mark.postgis
async def test_health_history_and_accuracy_endpoints(client, session):
    segment = await deteriorating_segment(session, days=(0, 5, 10, 15))
    await assess_segments(session, now=day(45))
    await evaluate_forecasts(session, now=day(53))

    history = (await client.get(f"/api/segments/{segment.id}/health")).json()
    assert len(history["history"]) == 5 and history["current"]["band"]
    assert history["history"][0]["measured_at"] < history["history"][-1]["measured_at"]

    accuracy = (await client.get("/api/forecast-accuracy")).json()
    row = next(r for r in accuracy["overall"]["horizons"] if r["horizon_days"] == 30)
    assert row["evaluated"] >= 1 and row["mean_absolute_error"] >= 0
    assert accuracy["recent"][0]["horizon_days"] == 30

    per_segment = (await client.get(f"/api/segments/{segment.id}/forecast")).json()
    assert per_segment["accuracy"]["horizons"]


@pytest.mark.postgis
async def test_health_endpoints_404_for_unknown_segment(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/segments/{missing}/health")).status_code == 404
    assert (await client.get(f"/api/segments/{missing}/forecast")).status_code == 404
