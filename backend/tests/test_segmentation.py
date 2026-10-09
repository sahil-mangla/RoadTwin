"""SPAT-01..03 end to end against Postgres."""

import datetime as dt
import math

import pytest
import sqlalchemy as sa

from backend.db.repository import DetectionRepository, ReportRepository
from backend.models.report import Report
from backend.models.road_segment import RoadSegment
from backend.services.spatial.segmentation import run_segmentation

LAT, LON = 12.9716, 77.5946
M = 111_195.0
T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def offset(north_m, east_m=0.0):
    return LAT + north_m / M, LON + east_m / (M * math.cos(math.radians(LAT)))


async def add_report(session, north_m, minutes=0, detected=True, perception="done"):
    lat, lon = offset(north_m)
    report = await ReportRepository(session).create(
        latitude=lat, longitude=lon, timestamp=T0, perception_status=perception,
        created_at=T0 + dt.timedelta(minutes=minutes),
    )
    if detected:
        await DetectionRepository(session).create(
            report_id=report.id, damage_type="D40", confidence=0.9,
            bbox_x1=0, bbox_y1=0, bbox_x2=10, bbox_y2=10, bbox_area_ratio=0.1, severity="low",
        )
    return report


async def segment_count(session):
    return await session.scalar(sa.select(sa.func.count()).select_from(RoadSegment))


@pytest.mark.postgis
async def test_duplicates_link_to_oldest_and_share_a_segment(session):
    a = await add_report(session, 0, minutes=1)
    b = await add_report(session, 4, minutes=2)
    summary = await run_segmentation(session)
    await session.refresh(a)
    await session.refresh(b)
    assert a.duplicate_of_id is None
    assert b.duplicate_of_id == a.id
    assert a.segment_id == b.segment_id is not None
    assert (summary.canonical_reports, summary.duplicates) == (1, 1)


@pytest.mark.postgis
async def test_nearby_damage_aggregates_into_one_segment_far_damage_into_another(session):
    near = [await add_report(session, n, minutes=i) for i, n in enumerate([0, 30, 60])]
    far = await add_report(session, 2000, minutes=9)
    await run_segmentation(session)
    for r in near + [far]:
        await session.refresh(r)
    assert len({r.segment_id for r in near}) == 1
    assert far.segment_id not in {r.segment_id for r in near}
    seg = await session.get(RoadSegment, near[0].segment_id)
    assert seg.length_meters == pytest.approx(60, rel=0.1)


@pytest.mark.postgis
async def test_ineligible_reports_are_left_out(session):
    no_damage = await add_report(session, 0, detected=False)
    pending = await add_report(session, 500, perception="pending")
    await run_segmentation(session)
    await session.refresh(no_damage)
    await session.refresh(pending)
    assert no_damage.segment_id is None and pending.segment_id is None
    assert await segment_count(session) == 0


@pytest.mark.postgis
async def test_rerun_reuses_segment_ids(session):
    reports = [await add_report(session, n, minutes=i) for i, n in enumerate([0, 30])]
    await run_segmentation(session)
    await session.refresh(reports[0])
    first_id = reports[0].segment_id

    second = await run_segmentation(session)
    await session.refresh(reports[0])
    assert reports[0].segment_id == first_id
    assert second.segments_created == 0
    assert await segment_count(session) == 1


@pytest.mark.postgis
async def test_new_report_extends_existing_segment_without_new_identity(session):
    first = await add_report(session, 0, minutes=1)
    await run_segmentation(session)
    await session.refresh(first)
    original = first.segment_id

    extra = await add_report(session, 40, minutes=5)
    await run_segmentation(session)
    await session.refresh(first)
    await session.refresh(extra)
    assert first.segment_id == extra.segment_id == original
    assert await segment_count(session) == 1
    seg = await session.get(RoadSegment, original)
    assert seg.length_meters == pytest.approx(40, rel=0.1)


@pytest.mark.postgis
async def test_segments_api_lists_with_counts(client, session):
    await add_report(session, 0, minutes=1)
    await add_report(session, 3, minutes=2)
    await run_segmentation(session)

    listing = (await client.get("/api/segments")).json()
    assert len(listing) == 1
    assert listing[0]["report_count"] == 2 and listing[0]["canonical_report_count"] == 1

    detail = (await client.get(f"/api/segments/{listing[0]['id']}")).json()
    assert len(detail["report_ids"]) == 2
    assert (await client.get("/api/segments/00000000-0000-0000-0000-000000000000")).status_code == 404
