"""PostGIS geometry round-trip test for SCHM-04.

Directly catches the axis-swap trap (01-RESEARCH.md Pitfall 1) by asserting
`ST_Y`/`ST_X` on the stored geometry equal the submitted latitude/longitude
-- rather than trusting `make_point()` without an independent DB-level
check.
"""

import datetime as dt

import pytest
import sqlalchemy as sa

from backend.db.repository import ReportRepository
from backend.models.enums import ReportStatus
from backend.models.report import Report


@pytest.mark.postgis
async def test_report_geometry_round_trips_with_correct_axis_order_and_srid(session):
    repo = ReportRepository(session)
    report = await repo.create(
        latitude=12.9716,
        longitude=77.5946,
        gps_accuracy_meters=8.5,
        timestamp=dt.datetime.now(dt.timezone.utc),
        source="citizen",
    )

    stmt = sa.select(
        sa.func.ST_Y(Report.location),
        sa.func.ST_X(Report.location),
        sa.func.ST_SRID(Report.location),
    ).where(Report.id == report.id)
    result = await session.execute(stmt)
    stored_lat, stored_lng, srid = result.one()

    assert stored_lat == pytest.approx(12.9716, abs=1e-6)
    assert stored_lng == pytest.approx(77.5946, abs=1e-6)
    assert srid == 4326


@pytest.mark.postgis
async def test_report_gps_accuracy_persists_and_defaults_to_none(session):
    repo = ReportRepository(session)

    with_accuracy = await repo.create(
        latitude=12.9716,
        longitude=77.5946,
        gps_accuracy_meters=8.5,
        timestamp=dt.datetime.now(dt.timezone.utc),
        source="citizen",
    )
    assert with_accuracy.gps_accuracy_meters == pytest.approx(8.5)

    without_accuracy = await repo.create(
        latitude=12.9716,
        longitude=77.5946,
        timestamp=dt.datetime.now(dt.timezone.utc),
        source="citizen",
    )
    assert without_accuracy.gps_accuracy_meters is None


@pytest.mark.postgis
async def test_report_status_defaults_to_unverified_on_real_insert(session):
    repo = ReportRepository(session)
    report = await repo.create(
        latitude=12.9716,
        longitude=77.5946,
        timestamp=dt.datetime.now(dt.timezone.utc),
        source="citizen",
    )

    assert report.status == ReportStatus.UNVERIFIED
