"""PERC-01..03: detections persisted per defect, idempotently, off the request path."""

import uuid

import pytest
import sqlalchemy as sa

from backend.db.repository import ReportRepository
from backend.models.detection import Detection
from backend.services.perception.detector import RawDetection, StubDetector
from backend.services.perception.pipeline import ReportNotFound, process_report

TWO_DEFECTS = [
    RawDetection("D40", 0.91, 10, 10, 60, 60),
    RawDetection("D00", 0.55, 0, 0, 100, 20),
]


async def _make_report(session):
    import datetime as dt

    return await ReportRepository(session).create(
        latitude=12.97, longitude=77.59, timestamp=dt.datetime.now(dt.timezone.utc)
    )


@pytest.mark.postgis
async def test_one_detection_row_per_defect(session, jpeg_bytes):
    report = await _make_report(session)
    count = await process_report(session, report.id, jpeg_bytes, StubDetector(TWO_DEFECTS))
    assert count == 2

    rows = (
        await session.scalars(sa.select(Detection).where(Detection.report_id == report.id))
    ).all()
    assert {r.damage_type for r in rows} == {"D40", "D00"}
    assert all(r.severity in {"low", "moderate", "high", "critical"} for r in rows)
    assert all(0 < r.bbox_area_ratio <= 1 for r in rows)
    assert report.perception_status == "done"


@pytest.mark.postgis
async def test_no_defects_is_done_with_zero_rows(session, jpeg_bytes):
    report = await _make_report(session)
    assert await process_report(session, report.id, jpeg_bytes, StubDetector()) == 0
    assert report.perception_status == "done"


@pytest.mark.postgis
async def test_retry_does_not_duplicate_detections(session, jpeg_bytes):
    report = await _make_report(session)
    detector = StubDetector(TWO_DEFECTS)
    await process_report(session, report.id, jpeg_bytes, detector)
    await process_report(session, report.id, jpeg_bytes, detector)

    count = await session.scalar(
        sa.select(sa.func.count()).select_from(Detection).where(Detection.report_id == report.id)
    )
    assert count == 2


@pytest.mark.postgis
async def test_missing_report_raises_for_retry(session, jpeg_bytes):
    with pytest.raises(ReportNotFound):
        await process_report(session, uuid.uuid4(), jpeg_bytes, StubDetector())


@pytest.mark.postgis
async def test_word_class_names_stored_as_codes(session, jpeg_bytes):
    report = await _make_report(session)
    detector = StubDetector([RawDetection("Potholes", 0.8, 0, 0, 50, 50)])
    await process_report(session, report.id, jpeg_bytes, detector)
    row = await session.scalar(sa.select(Detection).where(Detection.report_id == report.id))
    assert row.damage_type == "D40"
