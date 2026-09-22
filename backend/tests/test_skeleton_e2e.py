"""End-to-end skeleton test — written RED on purpose.

This is the phase's happy path: an operator submits a road report through
the API and immediately sees it listed back with its `unverified` status
and GPS accuracy. It must fail right now (no `backend.main` module exists
yet) and pass unchanged once Plan 02 mounts the skeleton router — do not
weaken this test later to make it pass.
"""

import uuid

import pytest


@pytest.mark.postgis
async def test_report_round_trips_through_the_api(client):
    payload = {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "gps_accuracy_meters": 8.5,
        "description": "pothole near the junction",
    }

    create_response = await client.post("/api/skeleton/reports", json=payload)
    assert create_response.status_code == 201

    body = create_response.json()
    assert uuid.UUID(body["id"])
    assert body["status"] == "unverified"
    assert body["gps_accuracy_meters"] == pytest.approx(8.5)
    assert body["latitude"] == pytest.approx(12.9716, abs=1e-6)
    assert body["longitude"] == pytest.approx(77.5946, abs=1e-6)

    list_response = await client.get("/api/skeleton/reports")
    assert list_response.status_code == 200
    ids = [row["id"] for row in list_response.json()]
    assert body["id"] in ids
