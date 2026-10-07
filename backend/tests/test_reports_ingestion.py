"""End-to-end tests for POST /api/reports and GET /api/reports/{id}/image-url.

INGT-01 (durable citizen submission) and INGT-04 (retrievable object
storage). Requires the compose Postgres service; tests that also touch
MinIO are additionally marked `minio`.
"""

import asyncio
import re
import uuid

import pytest
import sqlalchemy as sa

from backend.models.report import Report


async def _post_report(client, jpeg_bytes: bytes, **form_overrides):
    data = {
        "latitude": "12.9716",
        "longitude": "77.5946",
        "gps_accuracy_meters": "8.5",
        "description": "pothole near the junction",
        **form_overrides,
    }
    files = {"image": ("photo.jpg", jpeg_bytes, "image/jpeg")}
    return await client.post("/api/reports", data=data, files=files)


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_submit_report_success(client, session, jpeg_bytes):
    response = await _post_report(client, jpeg_bytes)
    assert response.status_code == 201, response.text
    body = response.json()
    uuid.UUID(body["id"])
    assert body["status"] == "unverified"
    assert body["source"] == "citizen"
    assert body["latitude"] == 12.9716
    assert "image_path" not in body

    row = await session.get(Report, uuid.UUID(body["id"]))
    assert row is not None
    assert re.fullmatch(r"reports/[0-9a-fA-F-]{36}\.jpg", row.image_path)


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_submit_report_invalid_gps(client, session, jpeg_bytes):
    response = await _post_report(client, jpeg_bytes, latitude="91")
    assert response.status_code == 422

    count = await session.scalar(sa.select(sa.func.count()).select_from(Report))
    assert count == 0


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_submit_report_missing_gps(client, jpeg_bytes):
    data = {"longitude": "77.5946"}
    files = {"image": ("photo.jpg", jpeg_bytes, "image/jpeg")}
    response = await client.post("/api/reports", data=data, files=files)
    assert response.status_code == 422


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_submit_report_accepts_poor_gps_accuracy(client, session, jpeg_bytes):
    response = await _post_report(client, jpeg_bytes, gps_accuracy_meters="250")
    assert response.status_code == 201, response.text
    row = await session.get(Report, uuid.UUID(response.json()["id"]))
    assert row.gps_accuracy_meters == 250


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_submit_report_timestamp_is_server_generated(client, session, jpeg_bytes):
    import datetime as dt

    data = {
        "latitude": "12.9716",
        "longitude": "77.5946",
        "timestamp": "1999-01-01T00:00:00Z",
    }
    files = {"image": ("photo.jpg", jpeg_bytes, "image/jpeg")}
    response = await client.post("/api/reports", data=data, files=files)
    assert response.status_code == 201, response.text

    row = await session.get(Report, uuid.UUID(response.json()["id"]))
    now = dt.datetime.now(dt.timezone.utc)
    assert abs((now - row.timestamp).total_seconds()) < 60


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_resubmitting_identical_payload_creates_independent_reports(
    client, session, jpeg_bytes
):
    # The second submission is offset ~1km away (well outside the
    # gps_cooldown_meters radius plan 02-04 later adds) so this test's
    # concern -- there is no CONTENT-based deduplication of the image/GPS
    # payload at ingestion -- stays isolated from the separate, deliberate
    # location-proximity throttling behavior test_rate_limit.py covers.
    # An identical payload at the SAME location within the cooldown window
    # is correctly rejected by that later control, not by this one.
    first = await _post_report(client, jpeg_bytes)
    second = await _post_report(client, jpeg_bytes, longitude="77.6046")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    first_row = await session.get(Report, uuid.UUID(first.json()["id"]))
    second_row = await session.get(Report, uuid.UUID(second.json()["id"]))
    assert first_row.image_path != second_row.image_path


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_concurrent_submissions_each_create_independent_rows(
    client_isolated_sessions, jpeg_bytes
):
    # Each concurrent request uses a distinct location (~1km apart), well
    # outside the GPS cooldown radius plan 02-04 adds -- this test's
    # concern is DB-level concurrency safety (no lost updates), which the
    # separate, deliberate location-proximity throttle would otherwise
    # confound if all three landed at the same spot.
    created_ids: list[str] = []
    try:
        responses = await asyncio.gather(
            *[
                _post_report(client_isolated_sessions, jpeg_bytes, longitude=str(77.5946 + i * 0.01))
                for i in range(3)
            ]
        )
        assert all(r.status_code == 201 for r in responses)
        ids = [r.json()["id"] for r in responses]
        created_ids = ids
        assert len(set(ids)) == 3
        image_paths = [r.json() for r in responses]
        assert len({r["id"] for r in image_paths}) == 3
    finally:
        from backend.db.session import async_session_factory

        async with async_session_factory() as cleanup_session:
            for report_id in created_ids:
                row = await cleanup_session.get(Report, uuid.UUID(report_id))
                if row is not None:
                    await cleanup_session.delete(row)
            await cleanup_session.commit()


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_image_url_404_for_unknown_report(client):
    response = await client.get(f"/api/reports/{uuid.uuid4()}/image-url")
    assert response.status_code == 404
