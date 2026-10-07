"""Tests for the dual-key rate limiter and GPS cooldown (INGT-03).

Thresholds are always read from `backend.core.config.settings`, never
hardcoded, so retuning a limit in Settings never breaks a test.
"""

import asyncio
import datetime as dt
import uuid

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa

from backend.core.config import settings
from backend.db.repository import ReportRepository, SubmissionAttemptRepository
from backend.models.rate_limit import SubmissionAttempt
from backend.models.report import Report

# Approximate metres-per-degree of longitude at ~13 deg latitude
# (used only to offset test fixture points by a known rough distance --
# not used anywhere in production code, which relies solely on PostGIS's
# own `ST_DWithin`/`Geography` distance math).
_METRES_PER_DEGREE_LONGITUDE_AT_13N = 108_000


def _client_with_ip(app, get_session, override, ip: str) -> httpx.AsyncClient:
    app.dependency_overrides[get_session] = override
    transport = httpx.ASGITransport(app=app, client=(ip, 0))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _post_report(client, jpeg_bytes: bytes, **overrides):
    data = {"latitude": "12.9716", "longitude": "77.5946", **overrides}
    files = {"image": ("photo.jpg", jpeg_bytes, "image/jpeg")}
    return await client.post("/api/reports", data=data, files=files)


@pytest_asyncio.fixture
async def app_and_session(session):
    """Exposes the pieces needed to build a client bound to a custom source IP."""
    from backend.db.session import get_session
    from backend.main import app

    async def _override_get_session():
        yield session

    yield app, get_session, _override_get_session, session, None
    app.dependency_overrides.pop(get_session, None)


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_identity_rate_limit_429(client, session, jpeg_bytes):
    identity_key = str(uuid.uuid4())
    for _ in range(settings.identity_rate_limit_per_hour):
        await SubmissionAttemptRepository(session).create(
            identity_key=identity_key, ip_address="198.51.100.1"
        )
    await session.flush()

    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
        cookies={"rt_device_id": _sign(identity_key)},
    )
    assert resp.status_code == 429
    retry_after = int(resp.headers["Retry-After"])
    assert retry_after > 0


def _sign(device_id: str) -> str:
    from backend.services.ingestion.identity import _get_serializer

    return _get_serializer().dumps(device_id)


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_identity_limit_boundary_allows_nth_rejects_n_plus_one(client, session, jpeg_bytes):
    identity_key = str(uuid.uuid4())
    n = settings.identity_rate_limit_per_hour

    for _ in range(n - 1):
        await SubmissionAttemptRepository(session).create(
            identity_key=identity_key, ip_address="198.51.100.2"
        )
    await session.flush()

    cookie = _sign(identity_key)
    ok_resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
        cookies={"rt_device_id": cookie},
    )
    assert ok_resp.status_code == 201, ok_resp.text

    # The Nth attempt row now exists (the accepted request above just
    # recorded it), so the (N+1)th request must be rejected.
    over_resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
        cookies={"rt_device_id": cookie},
    )
    assert over_resp.status_code == 429


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_attempts_outside_the_window_do_not_count(client, session, jpeg_bytes):
    identity_key = str(uuid.uuid4())
    old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        seconds=settings.rate_limit_window_seconds + 60
    )
    for _ in range(settings.identity_rate_limit_per_hour):
        await SubmissionAttemptRepository(session).create(
            identity_key=identity_key, ip_address="198.51.100.3", created_at=old_time
        )
    await session.flush()

    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
        cookies={"rt_device_id": _sign(identity_key)},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_window_boundary_is_inclusive(session):
    """Unit-level: a row exactly at `window_start` is counted (`>=`, not `>`).

    Time is frozen for `count_recent_attempts` so the row's `created_at`
    and the query's own `window_start` are computed against the identical
    instant -- a real-wall-clock version of this test is inherently racy
    by the milliseconds that elapse between inserting the row and the
    query running.
    """
    import types

    from backend.services.ingestion import rate_limit as rl

    frozen_now = dt.datetime.now(dt.timezone.utc)
    window_start = frozen_now - dt.timedelta(seconds=settings.rate_limit_window_seconds)

    class _FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now

    fake_dt = types.SimpleNamespace(
        datetime=_FixedDatetime, timezone=dt.timezone, timedelta=dt.timedelta
    )

    identity_key = str(uuid.uuid4())
    await SubmissionAttemptRepository(session).create(
        identity_key=identity_key, ip_address="198.51.100.4", created_at=window_start
    )
    await session.flush()

    import unittest.mock

    with unittest.mock.patch.object(rl, "dt", fake_dt):
        count = await rl.count_recent_attempts(
            session,
            column=SubmissionAttempt.identity_key,
            value=identity_key,
            window_seconds=settings.rate_limit_window_seconds,
        )
    assert count == 1


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_ip_rate_limit_429(app_and_session, jpeg_bytes):
    app, get_session, override, session, _ = app_and_session
    shared_ip = "203.0.113.9"
    for _ in range(settings.ip_rate_limit_per_hour):
        await SubmissionAttemptRepository(session).create(
            identity_key=str(uuid.uuid4()), ip_address=shared_ip
        )
    await session.flush()

    async with _client_with_ip(app, get_session, override, shared_ip) as ip_client:
        resp = await _post_report(ip_client, jpeg_bytes)
        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) > 0


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_gps_cooldown_429(client, session, jpeg_bytes):
    await ReportRepository(session).create(
        latitude=12.9716,
        longitude=77.5946,
        timestamp=dt.datetime.now(dt.timezone.utc),
        source="citizen",
    )
    await session.flush()

    offset = 5 / _METRES_PER_DEGREE_LONGITUDE_AT_13N
    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": str(77.5946 + offset)},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_gps_cooldown_is_measured_in_metres_not_degrees(client, session, jpeg_bytes):
    await ReportRepository(session).create(
        latitude=12.9716,
        longitude=77.5946,
        timestamp=dt.datetime.now(dt.timezone.utc),
        source="citizen",
    )
    await session.flush()

    near_offset = 5 / _METRES_PER_DEGREE_LONGITUDE_AT_13N
    near_resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": str(77.5946 + near_offset)},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert near_resp.status_code == 429

    far_offset = 200 / _METRES_PER_DEGREE_LONGITUDE_AT_13N
    far_resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": str(77.5946 + far_offset)},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert far_resp.status_code == 201, far_resp.text


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_gps_cooldown_expires(client, session, jpeg_bytes):
    old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        seconds=settings.gps_cooldown_seconds + 60
    )
    await ReportRepository(session).create(
        latitude=12.9716,
        longitude=77.5946,
        timestamp=old_time,
        source="citizen",
        created_at=old_time,
    )
    await session.flush()

    offset = 5 / _METRES_PER_DEGREE_LONGITUDE_AT_13N
    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": str(77.5946 + offset)},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_rate_limited_request_records_no_attempt_row(client, session, jpeg_bytes):
    identity_key = str(uuid.uuid4())
    for _ in range(settings.identity_rate_limit_per_hour):
        await SubmissionAttemptRepository(session).create(
            identity_key=identity_key, ip_address="198.51.100.5"
        )
    await session.flush()

    before = await session.scalar(sa.select(sa.func.count()).select_from(SubmissionAttempt))

    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
        cookies={"rt_device_id": _sign(identity_key)},
    )
    assert resp.status_code == 429

    after = await session.scalar(sa.select(sa.func.count()).select_from(SubmissionAttempt))
    assert after == before


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_accepted_submission_records_exactly_one_attempt_row(client, session, jpeg_bytes):
    before = await session.scalar(sa.select(sa.func.count()).select_from(SubmissionAttempt))

    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert resp.status_code == 201, resp.text

    after = await session.scalar(sa.select(sa.func.count()).select_from(SubmissionAttempt))
    assert after == before + 1

    row = await session.scalar(
        sa.select(SubmissionAttempt).order_by(SubmissionAttempt.created_at.desc()).limit(1)
    )
    assert row.identity_key
    assert row.ip_address


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_failed_report_insert_consumes_no_rate_limit_slot(client, session, jpeg_bytes, monkeypatch):
    from backend.db.repository import ReportRepository as RR

    async def _boom(self, **kwargs):
        raise RuntimeError("simulated insert failure")

    monkeypatch.setattr(RR, "create", _boom)

    before = await session.scalar(sa.select(sa.func.count()).select_from(SubmissionAttempt))

    with pytest.raises(Exception):
        await client.post(
            "/api/reports",
            data={"latitude": "12.9716", "longitude": "77.5946"},
            files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
        )

    after = await session.scalar(sa.select(sa.func.count()).select_from(SubmissionAttempt))
    assert after == before


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_rate_limit_rejection_happens_before_image_is_read(client, session, jpeg_bytes):
    identity_key = str(uuid.uuid4())
    for _ in range(settings.identity_rate_limit_per_hour):
        await SubmissionAttemptRepository(session).create(
            identity_key=identity_key, ip_address="198.51.100.6"
        )
    await session.flush()

    oversized = b"0" * (settings.max_upload_bytes + 1)
    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("big.jpg", oversized, "image/jpeg")},
        cookies={"rt_device_id": _sign(identity_key)},
    )
    # A 429 (not 413) proves the cheap Postgres checks ran before the
    # oversized upload stream was ever consumed.
    assert resp.status_code == 429


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_concurrent_submissions_may_exceed_limit_by_a_small_margin(
    client_isolated_sessions, jpeg_bytes
):
    """Documents the accepted TOCTOU residual risk (see must_haves.truths backstop).

    The COUNT-then-insert sequence is not atomic, so under true concurrency
    the effective limit can be exceeded by a small margin. This test
    asserts that accepted looseness -- at least N of N+3 concurrent
    requests succeed -- rather than asserting false exactness.
    """
    n = settings.identity_rate_limit_per_hour
    identity_key = str(uuid.uuid4())
    cookie = _sign(identity_key)
    client_isolated_sessions.cookies.set("rt_device_id", cookie)

    created_ids: list[str] = []
    try:
        responses = await asyncio.gather(
            *[_post_report(client_isolated_sessions, jpeg_bytes) for _ in range(n + 3)]
        )
        successes = [r for r in responses if r.status_code == 201]
        created_ids = [r.json()["id"] for r in successes]
        assert len(successes) >= n
    finally:
        from backend.db.session import async_session_factory

        async with async_session_factory() as cleanup_session:
            for report_id in created_ids:
                row = await cleanup_session.get(Report, uuid.UUID(report_id))
                if row is not None:
                    await cleanup_session.delete(row)
            await cleanup_session.execute(
                sa.delete(SubmissionAttempt).where(SubmissionAttempt.identity_key == identity_key)
            )
            await cleanup_session.commit()


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_prune_old_attempts_deletes_only_expired_rows(session):
    from backend.services.ingestion.rate_limit import prune_old_attempts

    expired_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        days=settings.submission_attempt_retention_days, seconds=60
    )
    recent_at = dt.datetime.now(dt.timezone.utc)

    await SubmissionAttemptRepository(session).create(
        identity_key=str(uuid.uuid4()), ip_address="198.51.100.30", created_at=expired_at
    )
    recent = await SubmissionAttemptRepository(session).create(
        identity_key=str(uuid.uuid4()), ip_address="198.51.100.31", created_at=recent_at
    )
    await session.flush()

    deleted = await prune_old_attempts(session)
    assert deleted == 1

    remaining = await session.scalar(
        sa.select(sa.func.count()).select_from(SubmissionAttempt).where(
            SubmissionAttempt.id == recent.id
        )
    )
    assert remaining == 1


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_prune_old_attempts_is_safe_on_empty_table(session):
    from backend.services.ingestion.rate_limit import prune_old_attempts

    await session.execute(sa.delete(SubmissionAttempt))
    await session.flush()

    deleted = await prune_old_attempts(session)
    assert deleted == 0


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_prune_does_not_touch_report_rows(session, jpeg_bytes):
    from backend.services.ingestion.rate_limit import prune_old_attempts

    before = await session.scalar(sa.select(sa.func.count()).select_from(Report))

    expired_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        days=settings.submission_attempt_retention_days, seconds=60
    )
    await SubmissionAttemptRepository(session).create(
        identity_key=str(uuid.uuid4()), ip_address="198.51.100.32", created_at=expired_at
    )
    await session.flush()

    await prune_old_attempts(session)

    after = await session.scalar(sa.select(sa.func.count()).select_from(Report))
    assert after == before
