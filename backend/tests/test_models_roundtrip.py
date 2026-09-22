"""SCHM-01 persistence and relationship coverage.

Builds one full seven-entity chain through the repositories in a single
test, proving the entities are distinct, related, and read back correctly
through a real PostGIS database -- not merely that the ORM classes import
without error.
"""

import datetime as dt
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.db.repository import (
    DetectionRepository,
    MaintenanceRecommendationRepository,
    PredictionRepository,
    ReportRepository,
    RoadHealthRepository,
    RoadObservationRepository,
    RoadSegmentRepository,
)
from backend.models.road_segment import RoadSegment


@pytest.mark.postgis
async def test_seven_entity_chain_persists_and_reads_back(session):
    segment_repo = RoadSegmentRepository(session)
    report_repo = ReportRepository(session)
    detection_repo = DetectionRepository(session)
    observation_repo = RoadObservationRepository(session)
    health_repo = RoadHealthRepository(session)
    prediction_repo = PredictionRepository(session)
    recommendation_repo = MaintenanceRecommendationRepository(session)

    now = dt.datetime.now(dt.timezone.utc)

    segment = await segment_repo.create(
        segment_identifier="SEG-TEST-0001",
        start_lat=12.9716,
        start_lng=77.5946,
        end_lat=12.9750,
        end_lng=77.5990,
    )

    report = await report_repo.create(
        latitude=12.9716,
        longitude=77.5946,
        timestamp=now,
    )

    detection = await detection_repo.create(
        report_id=report.id,
        damage_type="pothole",
        confidence=0.87,
        bbox_x1=0.1,
        bbox_y1=0.1,
        bbox_x2=0.3,
        bbox_y2=0.3,
        bbox_area_ratio=0.04,
    )

    observation = await observation_repo.create(
        road_segment_id=segment.id,
        report_id=report.id,
        detection_id=detection.id,
        observed_at=now,
        severity="moderate",
        damage_type="pothole",
        confidence=0.87,
    )

    health = await health_repo.create(
        road_segment_id=segment.id,
        measured_at=now,
        health_score=72.5,
    )

    prediction = await prediction_repo.create(
        road_segment_id=segment.id,
        generated_at=now,
        horizon_days=30,
        predicted_health_score=68.0,
        method="linear_regression",
    )

    recommendation = await recommendation_repo.create(
        road_segment_id=segment.id,
        priority_score=42.0,
        urgency="medium",
        recommended_action="patch pothole",
        explanation="Detected pothole with high confidence; segment health trending down.",
    )

    # Capture every id *before* expiring -- once expired, plain attribute
    # access (e.g. `segment.id`) would need to lazily reload through the
    # async engine, which raises `MissingGreenlet` outside of an awaited
    # call. Only ever touch already-captured plain values after this point.
    segment_id = segment.id
    report_id = report.id
    detection_id = detection.id
    observation_id = observation.id
    health_id = health.id
    prediction_id = prediction.id
    recommendation_id = recommendation.id

    await session.flush()
    session.expire_all()

    fetched_segment = await segment_repo.get(segment_id)
    fetched_report = await report_repo.get(report_id)
    fetched_detection = await detection_repo.get(detection_id)
    fetched_observation = await observation_repo.get(observation_id)
    fetched_health = await health_repo.get(health_id)
    fetched_prediction = await prediction_repo.get(prediction_id)
    fetched_recommendation = await recommendation_repo.get(recommendation_id)

    assert fetched_segment.id == segment_id
    assert fetched_report.id == report_id
    assert fetched_detection.id == detection_id
    assert fetched_observation.id == observation_id
    assert fetched_health.id == health_id
    assert fetched_prediction.id == prediction_id
    assert fetched_recommendation.id == recommendation_id

    detection_ids = {d.id for d in fetched_report.detections}
    assert detection_id in detection_ids

    observation_ids = {o.id for o in fetched_segment.observations}
    health_ids = {h.id for h in fetched_segment.health_records}
    prediction_ids = {p.id for p in fetched_segment.predictions}
    recommendation_ids = {r.id for r in fetched_segment.recommendations}

    assert observation_id in observation_ids
    assert health_id in health_ids
    assert prediction_id in prediction_ids
    assert recommendation_id in recommendation_ids

    srid = await session.execute(
        select(func.ST_SRID(RoadSegment.geometry)).where(RoadSegment.id == segment_id)
    )
    assert srid.scalar_one() == 4326


@pytest.mark.postgis
async def test_road_observation_rejects_nonexistent_segment(session):
    observation_repo = RoadObservationRepository(session)
    report_repo = ReportRepository(session)

    now = dt.datetime.now(dt.timezone.utc)
    report = await report_repo.create(
        latitude=12.9716,
        longitude=77.5946,
        timestamp=now,
    )
    await session.flush()

    # Wrapped in a SAVEPOINT so the expected constraint violation only
    # rolls back this one statement, not the fixture's outer transaction
    # (which must remain usable for the test's own teardown). The
    # exception must propagate *out of* `begin_nested()`'s context
    # manager for it to roll back to the savepoint correctly, so
    # `pytest.raises` wraps the whole block rather than sitting inside it.
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            # BaseRepository.create() flushes internally, so the
            # constraint violation surfaces from inside this call.
            await observation_repo.create(
                road_segment_id=uuid.uuid4(),
                report_id=report.id,
                observed_at=now,
            )
