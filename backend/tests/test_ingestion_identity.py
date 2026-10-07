"""Tests for the signed device-identity cookie (INGT-02).

Covers mint/reuse, tamper/expiry re-mint, cookie hardening, the
cookies-blocked fallback, and the privacy prohibition that the identity is
never echoed back to the client.
"""

import uuid

import pytest


async def _post_report(
    client, jpeg_bytes: bytes, cookies: dict | None = None, longitude: str = "77.5946"
):
    data = {"latitude": "12.9716", "longitude": longitude}
    files = {"image": ("photo.jpg", jpeg_bytes, "image/jpeg")}
    return await client.post("/api/reports", data=data, files=files, cookies=cookies or {})


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_device_id_mint_and_reuse(client, session, jpeg_bytes):
    from backend.models.report import Report

    first = await _post_report(client, jpeg_bytes)
    assert first.status_code == 201, first.text
    assert "rt_device_id" in first.cookies

    # Offset ~1km away, outside plan 02-04's GPS cooldown radius -- this
    # test is about identity reuse, not location, and the two requests
    # would otherwise trip the cooldown against each other.
    cookie_value = first.cookies["rt_device_id"]
    second = await _post_report(
        client, jpeg_bytes, cookies={"rt_device_id": cookie_value}, longitude="77.6046"
    )
    assert second.status_code == 201, second.text
    assert "rt_device_id" not in second.cookies

    first_row = await session.get(Report, uuid.UUID(first.json()["id"]))
    second_row = await session.get(Report, uuid.UUID(second.json()["id"]))
    assert first_row.submitter_identity_key == second_row.submitter_identity_key


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_tampered_cookie_remints(client, session, jpeg_bytes):
    from backend.models.report import Report

    first = await _post_report(client, jpeg_bytes)
    real_cookie = first.cookies["rt_device_id"]
    tampered = real_cookie[:-1] + ("A" if real_cookie[-1] != "A" else "B")

    resp = await _post_report(
        client, jpeg_bytes, cookies={"rt_device_id": tampered}, longitude="77.6046"
    )
    assert resp.status_code == 201, resp.text
    assert "rt_device_id" in resp.cookies

    first_row = await session.get(Report, uuid.UUID(first.json()["id"]))
    second_row = await session.get(Report, uuid.UUID(resp.json()["id"]))
    assert first_row.submitter_identity_key != second_row.submitter_identity_key


def test_expired_cookie_remints(monkeypatch):
    """Unit-level: a cookie older than `device_id_cookie_max_age_seconds` re-mints."""
    import time

    from backend.core.config import settings
    from backend.services.ingestion import identity as identity_module

    identity_module._get_serializer.cache_clear()
    serializer = identity_module._get_serializer()
    original_id = str(uuid.uuid4())
    signed = serializer.dumps(original_id)

    time.sleep(1.1)
    # itsdangerous compares integer-second timestamps, so max_age=0 is used
    # (rather than 1) to guarantee the elapsed >1s sleep always exceeds it,
    # regardless of where the sleep lands relative to a second boundary.
    monkeypatch.setattr(settings, "device_id_cookie_max_age_seconds", 0)

    device_id, new_signed = identity_module.read_or_mint_device_id(signed)
    assert device_id != original_id
    assert new_signed is not None


@pytest.mark.asyncio
async def test_cookie_attributes_are_hardened(client, jpeg_bytes):
    from backend.core.config import settings

    resp = await _post_report(client, jpeg_bytes)
    set_cookie_header = resp.headers.get_list("set-cookie")
    assert any("rt_device_id" in h for h in set_cookie_header)
    device_cookie_header = next(h for h in set_cookie_header if "rt_device_id" in h)
    assert "HttpOnly" in device_cookie_header
    assert "samesite=lax" in device_cookie_header.lower()
    if settings.device_id_cookie_secure:
        assert "Secure" in device_cookie_header
    else:
        assert "Secure" not in device_cookie_header


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_submission_without_cookie_support_still_succeeds(client, session, jpeg_bytes):
    from backend.models.report import Report

    first = await _post_report(client, jpeg_bytes)
    client.cookies.clear()  # simulate a client that never persists cookies
    second = await _post_report(client, jpeg_bytes, longitude="77.6046")
    assert first.status_code == 201
    assert second.status_code == 201

    first_row = await session.get(Report, uuid.UUID(first.json()["id"]))
    second_row = await session.get(Report, uuid.UUID(second.json()["id"]))
    assert first_row.submitter_identity_key != second_row.submitter_identity_key


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_report_row_carries_submitter_identity(client, session, jpeg_bytes):
    from backend.models.report import Report

    resp = await _post_report(client, jpeg_bytes)
    row = await session.get(Report, uuid.UUID(resp.json()["id"]))
    assert row.submitter_identity_key is not None
    assert len(row.submitter_identity_key) == 36


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_signed_cookie_value_is_not_the_bare_identity(client, session, jpeg_bytes):
    from backend.models.report import Report

    resp = await _post_report(client, jpeg_bytes)
    row = await session.get(Report, uuid.UUID(resp.json()["id"]))
    assert resp.cookies["rt_device_id"] != row.submitter_identity_key


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_identity_is_not_echoed_in_api_responses(client, jpeg_bytes):
    resp = await _post_report(client, jpeg_bytes)
    body = resp.text.lower()
    assert "identity" not in body
