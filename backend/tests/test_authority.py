"""AUTH-01..06, PRIO-01..03, PMAP-01..02, RPWF-01..02."""

import datetime as dt

import pytest
import sqlalchemy as sa

from backend.db.repository import (
    DetectionRepository,
    ReportRepository,
    RoadObservationRepository,
    RoadSegmentRepository,
)
from backend.models.authority import STAFF_ROLE, CitizenNotification, RepairEvent, StaffUser
from backend.models.maintenance_recommendation import MaintenanceRecommendation
from backend.services.authority.auth import hash_password, reset_login_throttle
from backend.services.intelligence.assessment import assess_segments
from backend.services.maintenance.prioritize import prioritize_segments

PASSWORD = "correct horse battery staple"
T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def _fresh_throttle():
    reset_login_throttle()
    yield
    reset_login_throttle()


async def make_staff(session, email="staff@city.gov", role=STAFF_ROLE, active=True):
    user = StaffUser(email=email, password_hash=hash_password(PASSWORD), role=role, is_active=active)
    session.add(user)
    await session.flush()
    return user


async def login(client, email="staff@city.gov", password=PASSWORD):
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def make_segment(session, ident, lat=13.0, severity="high", n=1, identity="citizen"):
    seg = await RoadSegmentRepository(session).create(
        segment_identifier=ident, start_lat=lat, start_lng=77.6, end_lat=lat + 0.001,
        end_lng=77.6, length_meters=110.0,
    )
    for i in range(n):
        when = T0 + dt.timedelta(days=i)
        report = await ReportRepository(session).create(
            latitude=lat, longitude=77.6, timestamp=when, perception_status="done",
            submitter_identity_key=f"{identity}-{ident}-{i}", segment_id=seg.id,
        )
        det = await DetectionRepository(session).create(
            report_id=report.id, damage_type="D40", confidence=0.9, bbox_x1=0, bbox_y1=0,
            bbox_x2=1, bbox_y2=1, bbox_area_ratio=0.1, severity=severity,
        )
        await RoadObservationRepository(session).create(
            road_segment_id=seg.id, report_id=report.id, detection_id=det.id, observed_at=when,
            severity=severity, damage_type="D40", confidence=0.9, verification_score=0.9,
            recorded_at=when,
        )
    return seg


async def assess_and_rank(session, now=T0 + dt.timedelta(days=3)):
    await assess_segments(session, now=now)
    return await prioritize_segments(session, now=now)


# --- AUTH-01 / AUTH-02 -------------------------------------------------------

@pytest.mark.postgis
@pytest.mark.parametrize("path", ["/api/authority/overview", "/api/authority/queue", "/api/auth/me"])
async def test_authority_endpoints_reject_anonymous_requests(client, path):
    assert (await client.get(path)).status_code == 401


@pytest.mark.postgis
async def test_anonymous_cannot_change_repair_status(client, session):
    seg = await make_segment(session, "SEG-A")
    response = await client.post(f"/api/authority/segments/{seg.id}/repair-status", json={"status": "received"})
    assert response.status_code == 401
    assert seg.repair_status == "none"


@pytest.mark.postgis
async def test_staff_login_grants_access_and_logout_revokes_it(client, session):
    await make_staff(session)
    response = await login(client)
    assert response.status_code == 200 and response.json()["role"] == "authority_staff"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert (await client.get("/api/auth/me")).status_code == 200

    await client.post("/api/auth/logout")
    assert (await client.get("/api/authority/overview")).status_code == 401


@pytest.mark.postgis
async def test_wrong_password_and_unknown_email_look_the_same(client, session):
    await make_staff(session)
    wrong = await login(client, password="nope")
    unknown = await login(client, email="nobody@city.gov")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@pytest.mark.postgis
async def test_repeated_failed_logins_are_throttled(client, session):
    await make_staff(session)
    codes = [(await login(client, password="bad")).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    assert (await login(client)).status_code == 429  # even the right password, until the window passes


@pytest.mark.postgis
async def test_inactive_or_non_staff_accounts_cannot_log_in(client, session):
    await make_staff(session, email="gone@city.gov", active=False)
    await make_staff(session, email="viewer@city.gov", role="viewer")
    assert (await login(client, email="gone@city.gov")).status_code == 401
    assert (await login(client, email="viewer@city.gov")).status_code == 401


@pytest.mark.postgis
async def test_forged_session_cookie_is_rejected(client, session):
    from backend.core.config import settings

    client.cookies.set(settings.staff_session_cookie_name, "forged.value.here")
    assert (await client.get("/api/authority/overview")).status_code == 401


# --- PRIO-01..03 / AUTH-03..06 ----------------------------------------------

@pytest.mark.postgis
async def test_queue_ranks_worse_roads_first_with_explanations(client, session):
    await make_segment(session, "SEG-MILD", lat=13.0, severity="low", n=1)
    await make_segment(session, "SEG-BAD", lat=13.1, severity="critical", n=3)
    summary = await assess_and_rank(session)
    assert summary.recommendations == 2

    await make_staff(session)
    await login(client)
    queue = (await client.get("/api/authority/queue")).json()
    assert [q["segment_identifier"] for q in queue] == ["SEG-BAD", "SEG-MILD"]
    assert [q["rank"] for q in queue] == [1, 2]
    assert queue[0]["priority_score"] > queue[1]["priority_score"]
    for item in queue:
        assert item["explanation"].startswith("Priority") and "Provisional" in item["explanation"]
        assert item["recommended_action"]


@pytest.mark.postgis
async def test_unchanged_priority_is_not_rewritten(session):
    await make_segment(session, "SEG-A")
    await assess_and_rank(session)
    again = await prioritize_segments(session, now=T0 + dt.timedelta(days=3))
    assert again.recommendations == 0


@pytest.mark.postgis
async def test_enhancement_inputs_change_the_priority(client, session):
    seg = await make_segment(session, "SEG-A", severity="moderate")
    await assess_and_rank(session)
    await make_staff(session)
    await login(client)
    before = (await client.get("/api/authority/queue")).json()[0]["priority_score"]

    patched = await client.patch(
        f"/api/authority/segments/{seg.id}/inputs",
        json={"traffic_exposure": 1.0, "road_type": "arterial", "near_vulnerable_location": True},
    )
    assert patched.status_code == 200 and patched.json()["traffic_exposure"] == 1.0
    await prioritize_segments(session, now=T0 + dt.timedelta(days=3))
    after = (await client.get("/api/authority/queue")).json()[0]
    assert after["priority_score"] > before
    for supplied in ("traffic exposure", "road importance", "nearby vulnerable locations"):
        assert supplied not in after["explanation"].split("No data for:")[-1]


@pytest.mark.postgis
async def test_overview_counts(client, session):
    await make_segment(session, "SEG-A", severity="low")
    await make_segment(session, "SEG-B", lat=13.2, severity="critical", n=6)
    await assess_and_rank(session)
    await make_staff(session)
    await login(client)
    body = (await client.get("/api/authority/overview")).json()
    assert body["segments"] == 2 and body["assessed_segments"] == 2
    assert sum(body["band_counts"].values()) == 2
    assert body["average_health"] is not None
    assert len(body["top_priorities"]) == 2
    assert "provisional" in body["note"].lower()
    assert set(body) >= {"critical_roads", "rapidly_deteriorating", "predicted_failures"}


@pytest.mark.postgis
async def test_segment_detail_has_history_composition_evidence_forecast_and_explanation(client, session):
    seg = await make_segment(session, "SEG-A", n=2)
    await assess_and_rank(session)
    await make_staff(session)
    await login(client)
    detail = (await client.get(f"/api/authority/segments/{seg.id}")).json()
    assert len(detail["health_history"]) == 1
    assert detail["damage_composition"] == {"D40": {"high": 2}}
    assert len(detail["evidence"]) == 2 and all(e["counts_toward_health"] for e in detail["evidence"])
    assert detail["outlook"]["forecast"]["status"] == "insufficient_data"
    assert detail["priority"]["explanation"] and detail["priority"]["components"]["contributions"]
    assert len(detail["reports"]) == 2
    assert (await client.get("/api/authority/segments/00000000-0000-0000-0000-000000000000")).status_code == 404


# --- RPWF-01 / RPWF-02 -------------------------------------------------------

@pytest.mark.postgis
async def test_repair_workflow_transitions_logs_and_notifies(client, session):
    seg = await make_segment(session, "SEG-A", n=2)
    await assess_and_rank(session)
    await make_staff(session)
    await login(client)

    for status in ("received", "in_progress", "resolved"):
        response = await client.post(
            f"/api/authority/segments/{seg.id}/repair-status", json={"status": status, "note": "crew 4"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["repair_status"] == status
        assert response.json()["citizens_notified"] == 2

    events = (await session.scalars(sa.select(RepairEvent).order_by(RepairEvent.created_at))).all()
    assert [(e.from_status, e.to_status) for e in events] == [
        ("none", "received"), ("received", "in_progress"), ("in_progress", "resolved")
    ]
    notes = (await session.scalars(sa.select(CitizenNotification))).all()
    assert len(notes) == 6 and any("Resolved" in n.message for n in notes)
    assert seg.last_repaired_at is not None


@pytest.mark.postgis
async def test_invalid_transition_is_rejected(client, session):
    seg = await make_segment(session, "SEG-A")
    await make_staff(session)
    await login(client)
    await client.post(f"/api/authority/segments/{seg.id}/repair-status", json={"status": "resolved"})
    response = await client.post(f"/api/authority/segments/{seg.id}/repair-status", json={"status": "in_progress"})
    assert response.status_code == 409
    bad = await client.post(f"/api/authority/segments/{seg.id}/repair-status", json={"status": "teleported"})
    assert bad.status_code == 422


@pytest.mark.postgis
async def test_resolving_a_road_resets_its_health(client, session):
    seg = await make_segment(session, "SEG-A", severity="critical", n=3)
    await assess_and_rank(session)
    damaged = seg.current_health_score
    assert damaged < 100

    await make_staff(session)
    await login(client)
    await client.post(f"/api/authority/segments/{seg.id}/repair-status", json={"status": "resolved"})
    await assess_and_rank(session, now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1))
    assert seg.current_health_score == 100
    rec = (await session.scalars(
        sa.select(MaintenanceRecommendation).order_by(MaintenanceRecommendation.generated_at.desc())
    )).first()
    assert rec.urgency == "low"


@pytest.mark.postgis
async def test_citizen_sees_only_their_own_notifications(client, session):
    seg = await make_segment(session, "SEG-A")
    staff = await make_staff(session)
    from backend.services.authority.repair import transition_repair_status

    # The client's own device id is minted on its first request.
    await client.get("/api/me/notifications")
    from backend.core.config import settings
    from backend.services.ingestion.identity import read_or_mint_device_id

    my_id, _ = read_or_mint_device_id(client.cookies.get(settings.device_id_cookie_name))
    mine = await ReportRepository(session).create(
        latitude=13.0, longitude=77.6, timestamp=T0, perception_status="done",
        submitter_identity_key=my_id, segment_id=seg.id,
    )
    await transition_repair_status(session, seg, "received", staff)

    notes = (await client.get("/api/me/notifications")).json()
    assert len(notes) == 1 and notes[0]["report_id"] == str(mine.id)
    assert notes[0]["read"] is False and "Received" in notes[0]["message"]

    assert (await client.post(f"/api/me/notifications/{notes[0]['id']}/read")).status_code == 204
    assert (await client.get("/api/me/notifications")).json()[0]["read"] is True

    other = (await session.scalars(
        sa.select(CitizenNotification).where(CitizenNotification.identity_key != my_id)
    )).first()
    assert (await client.post(f"/api/me/notifications/{other.id}/read")).status_code == 404


# --- PMAP-01 / PMAP-02 -------------------------------------------------------

@pytest.mark.postgis
async def test_public_map_is_open_read_only_and_leaks_no_identities(client, session):
    seg = await make_segment(session, "SEG-A", n=2, identity="secret-device")
    await assess_and_rank(session)

    body = (await client.get("/api/public/map")).json()
    assert "provisional" in body["note"].lower()
    assert body["segments"][0]["band"] and body["segments"][0]["trend"] == "insufficient data"
    assert len(body["reports"]) == 2 and body["reports"][0]["damage_types"] == ["D40"]
    assert "secret-device" not in (await client.get("/api/public/map")).text

    detail = (await client.get(f"/api/public/segments/{seg.id}")).json()
    assert detail["health_history"] and detail["damage_composition"] == {"D40": 2}
    assert "explanation" not in str(detail["segment"])

    assert (await client.post("/api/public/map")).status_code == 405
