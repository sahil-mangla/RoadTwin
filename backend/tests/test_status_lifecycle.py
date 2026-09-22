"""SCHM-03: the Report/Detection status lifecycle (D-06).

Covers: both entities default to `unverified` on arrival without being
told to; all four D-06 enum values (including the reserved `rejected`
member) are settable and persist; an out-of-enum value is rejected at the
Postgres level, not merely by the Python type; and Report/Detection share
one Postgres enum type, not two.
"""

import datetime as dt

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from backend.db.repository import DetectionRepository, ReportRepository
from backend.models.detection import Detection
from backend.models.enums import ReportStatus
from backend.models.geo import make_point
from backend.models.report import Report


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def _make_report(session, **overrides):
    fields = dict(
        latitude=12.9716,
        longitude=77.5946,
        gps_accuracy_meters=5.0,
        timestamp=_now(),
        location=make_point(12.9716, 77.5946),
    )
    fields.update(overrides)
    return await ReportRepository(session).create(**fields)


@pytest.mark.postgis
async def test_report_defaults_to_unverified_on_arrival(session):
    report = await _make_report(session)
    assert report.status == ReportStatus.UNVERIFIED


@pytest.mark.postgis
async def test_detection_defaults_to_unverified_on_arrival(session):
    report = await _make_report(session)
    detection = await DetectionRepository(session).create(
        report_id=report.id,
        damage_type="pothole",
        confidence=0.7,
        bbox_x1=1.0,
        bbox_y1=1.0,
        bbox_x2=2.0,
        bbox_y2=2.0,
        bbox_area_ratio=0.1,
    )
    assert detection.status == ReportStatus.UNVERIFIED


@pytest.mark.postgis
async def test_all_four_lifecycle_values_are_settable_and_persist(session):
    report = await _make_report(session)
    repo = ReportRepository(session)

    # All four D-06 values, including the reserved `rejected` member, must
    # round-trip -- not just the three values the skeleton UI exercises.
    for value in ReportStatus:
        updated = await repo.update(report, status=value)
        assert updated.status == value
        reloaded = await repo.get(report.id)
        assert reloaded is not None
        assert reloaded.status == value


@pytest.mark.postgis
async def test_status_out_of_enum_is_rejected_at_the_database_level(session):
    report = await _make_report(session)

    # Bypasses the ORM's Python-side Enum validation on purpose, so this
    # proves Postgres itself rejects the value -- not merely the Python
    # type. The literal below is a fixed test value, not interpolated from
    # a variable (threat T-01-03's no-string-interpolation rule still
    # holds: `report_id` is bound as a parameter).
    with pytest.raises(DBAPIError):
        await session.execute(
            sa.text("UPDATE report SET status = 'bogus_status' WHERE id = :report_id"),
            {"report_id": report.id},
        )
        await session.flush()


@pytest.mark.postgis
async def test_report_and_detection_share_the_same_postgres_enum_type():
    report_type = Report.__table__.c.status.type
    detection_type = Detection.__table__.c.status.type
    assert report_type.name == detection_type.name == "report_status"
    # Object identity, not merely matching names -- the same `sa.Enum`
    # instance is reused (Pattern 3), guaranteeing exactly one `CREATE
    # TYPE` across both migrations.
    assert report_type is detection_type
