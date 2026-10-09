"""EVID-01..04, HLTH-01 end to end against Postgres."""

import datetime as dt
import logging
import math

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from backend.db.repository import (
    DetectionRepository,
    ReportCorroborationRepository,
    ReportRepository,
)
from backend.models.enums import ReportStatus
from backend.models.road_observation import RoadObservation
from backend.services.intelligence.observations import record_observations
from backend.services.spatial.segmentation import run_segmentation

LAT, LON = 12.9716, 77.5946
T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


async def add_report(session, identity, day=0, north_m=0.0, confidence=0.9):
    report = await ReportRepository(session).create(
        latitude=LAT + north_m / 111_195.0,
        longitude=LON,
        timestamp=T0 + dt.timedelta(days=day),
        created_at=T0 + dt.timedelta(days=day),
        submitter_identity_key=identity,
        perception_status="done",
    )
    await DetectionRepository(session).create(
        report_id=report.id, damage_type="D40", confidence=confidence,
        bbox_x1=0, bbox_y1=0, bbox_x2=10, bbox_y2=10, bbox_area_ratio=0.1, severity="moderate",
    )
    return report


async def vote(session, report, identity):
    await ReportCorroborationRepository(session).create(
        report_id=report.id, identity_key=identity, ip_address="203.0.113.1"
    )


async def run(session):
    await run_segmentation(session)
    return await record_observations(session)


async def observations(session):
    return (
        await session.scalars(sa.select(RoadObservation).order_by(RoadObservation.recorded_at))
    ).all()


@pytest.mark.postgis
async def test_lone_report_gets_a_modest_score_and_stays_unverified(session):
    report = await add_report(session, "alice", confidence=1.0)
    await run(session)
    await session.refresh(report)
    assert report.verification_score == pytest.approx(0.35)
    assert report.status == ReportStatus.UNVERIFIED
    (obs,) = await observations(session)
    assert obs.road_segment_id == report.segment_id
    assert set(obs.evidence_components["components"]) == {
        "ml_confidence", "observation_count", "spatial_agreement",
        "temporal_consistency", "community_validation",
    }


@pytest.mark.postgis
async def test_same_identity_reporting_twice_is_not_independent_evidence(session):
    lone = await add_report(session, "alice", day=0, north_m=2000)
    first = await add_report(session, "bob", day=0)
    again = await add_report(session, "bob", day=6)  # bob re-reports a week later
    await run(session)
    for r in (lone, first, again):
        await session.refresh(r)
    assert first.verification_score == pytest.approx(lone.verification_score)
    assert again.status == ReportStatus.UNVERIFIED


@pytest.mark.postgis
async def test_two_independent_reporters_corroborate_each_other(session):
    a = await add_report(session, "alice", day=0)
    b = await add_report(session, "bob", day=2, north_m=3)
    await run(session)
    for r in (a, b):
        await session.refresh(r)
    assert a.status == b.status == ReportStatus.CORROBORATED
    assert a.verification_score > 0.35


@pytest.mark.postgis
async def test_strong_evidence_confirms_the_report(session):
    reports = [await add_report(session, f"user{i}", day=i * 3, north_m=i) for i in range(4)]
    for voter in ("v1", "v2", "v3"):
        await vote(session, reports[0], voter)
    await run(session)
    for r in reports:
        await session.refresh(r)
    assert all(r.status == ReportStatus.EVIDENCE_CONFIRMED for r in reports)
    assert reports[0].verification_score >= 0.7
    assert reports[0].community_upvotes == 3


@pytest.mark.postgis
async def test_an_identity_can_corroborate_a_report_only_once(session):
    report = await add_report(session, "alice")
    await vote(session, report, "voter")
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await vote(session, report, "voter")


@pytest.mark.postgis
async def test_a_submitters_own_vote_does_not_add_community_evidence(session):
    report = await add_report(session, "alice", confidence=1.0)
    await vote(session, report, "alice")
    await run(session)
    await session.refresh(report)
    assert report.verification_score == pytest.approx(0.35)


@pytest.mark.postgis
async def test_history_accumulates_and_rerun_adds_nothing(session):
    a = await add_report(session, "alice", day=0)
    summary = await run(session)
    assert summary.observations_recorded == 1

    b = await add_report(session, "bob", day=5, north_m=2)
    summary = await run(session)
    assert summary.observations_recorded >= 1  # bob's detection (+ alice's re-score)
    rows = await observations(session)
    assert len({o.report_id for o in rows}) == 2
    assert len({o.road_segment_id for o in rows}) == 1

    assert (await run(session)).observations_recorded == 0  # idempotent


@pytest.mark.postgis
async def test_score_change_appends_a_snapshot_instead_of_overwriting(session):
    report = await add_report(session, "alice")
    await run(session)
    before = (await observations(session))[0]
    first_score = before.verification_score

    for voter in ("v1", "v2", "v3"):
        await vote(session, report, voter)
    await run(session)
    rows = await observations(session)
    assert len(rows) == 2
    assert rows[0].verification_score == first_score  # the old row is untouched
    assert rows[1].verification_score > first_score


@pytest.mark.postgis
async def test_component_contributions_are_logged(session, caplog):
    await add_report(session, "alice")
    # Alembic's fileConfig (run by the migration fixture) disables loggers
    # that already exist; switch this one back on.
    target = logging.getLogger("backend.services.intelligence.observations")
    target.disabled = False
    with caplog.at_level(logging.INFO, logger=target.name):
        await run(session)
    line = next(r.message for r in caplog.records if r.message.startswith("evidence"))
    for name in ("ml_confidence", "observation_count", "spatial_agreement",
                 "temporal_consistency", "community_validation"):
        assert f"{name}=" in line


@pytest.mark.postgis
async def test_observation_history_api(client, session):
    await add_report(session, "alice", day=0)
    b = await add_report(session, "bob", day=4, north_m=2)
    await run(session)
    await vote(session, b, "v1")
    await vote(session, b, "v2")
    await vote(session, b, "v3")
    await run(session)

    segment_id = (await client.get("/api/segments")).json()[0]["id"]
    full = (await client.get(f"/api/segments/{segment_id}/observations")).json()
    latest = (await client.get(f"/api/segments/{segment_id}/observations?latest_only=true")).json()
    assert len(full) > len(latest) == 2
    assert all(o["evidence_components"] for o in full)
    assert (await client.get("/api/segments/00000000-0000-0000-0000-000000000000/observations")).status_code == 404


@pytest.mark.postgis
async def test_corroborate_endpoint_counts_once_per_device(client, session):
    report = await add_report(session, "someone-else")
    first = await client.post(f"/api/reports/{report.id}/corroborate")
    again = await client.post(f"/api/reports/{report.id}/corroborate")
    assert first.status_code == again.status_code == 200
    assert first.json() == {"counted": True, "community_upvotes": 1}
    assert again.json() == {"counted": False, "community_upvotes": 1}


@pytest.mark.postgis
async def test_corroborate_unknown_report_is_404(client):
    response = await client.post("/api/reports/00000000-0000-0000-0000-000000000000/corroborate")
    assert response.status_code == 404


@pytest.mark.postgis
@pytest.mark.minio
async def test_cannot_corroborate_your_own_report(client, jpeg_bytes):
    submitted = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("p.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert submitted.status_code == 201, submitted.text
    response = await client.post(f"/api/reports/{submitted.json()['id']}/corroborate")
    assert response.status_code == 409


@pytest.mark.postgis
async def test_corroborations_are_rate_limited_per_ip(client, session, monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "corroboration_ip_limit_per_hour", 2)
    reports = [await add_report(session, f"u{i}", north_m=i * 1000) for i in range(3)]
    codes = [(await client.post(f"/api/reports/{r.id}/corroborate")).status_code for r in reports]
    assert codes == [200, 200, 429]
