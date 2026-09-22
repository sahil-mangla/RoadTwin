"""SCHM-01 + SCHM-02 through the HTTP surface.

Covers the chain-seed endpoint (one linked row in all seven tables per
call), the schema-status endpoint (live per-entity row counts), repeated
seeding growing the three append-only tables rather than replacing rows,
and the status-transition endpoint persisting a change through a
follow-up GET.
"""

import uuid

import pytest

_ENTITY_NAMES = {
    "report",
    "detection",
    "road_segment",
    "road_observation",
    "road_health",
    "prediction",
    "maintenance_recommendation",
}

_APPEND_ONLY_ENTITIES = ("road_observation", "road_health", "prediction")


@pytest.mark.postgis
async def test_schema_status_lists_exactly_seven_entities(client):
    response = await client.get("/api/skeleton/schema-status")
    assert response.status_code == 200
    body = response.json()
    assert len(body["entities"]) == 7
    names = {row["entity"] for row in body["entities"]}
    assert names == _ENTITY_NAMES


@pytest.mark.postgis
async def test_chain_seed_returns_seven_distinct_uuids(client):
    response = await client.post("/api/skeleton/chain")
    assert response.status_code == 201
    body = response.json()
    ids = [
        body["report_id"],
        body["detection_id"],
        body["road_segment_id"],
        body["road_observation_id"],
        body["road_health_id"],
        body["prediction_id"],
        body["maintenance_recommendation_id"],
    ]
    assert all(ids)
    for value in ids:
        assert uuid.UUID(value)
    assert len(set(ids)) == 7


@pytest.mark.postgis
async def test_chain_seed_grows_every_entity_count_by_at_least_one(client):
    before = (await client.get("/api/skeleton/schema-status")).json()
    before_counts = {row["entity"]: row["count"] for row in before["entities"]}

    seed_response = await client.post("/api/skeleton/chain")
    assert seed_response.status_code == 201

    after = (await client.get("/api/skeleton/schema-status")).json()
    after_counts = {row["entity"]: row["count"] for row in after["entities"]}

    for entity, count in before_counts.items():
        assert after_counts[entity] >= count + 1, entity


@pytest.mark.postgis
async def test_seeding_twice_grows_append_only_counts_again(client):
    """SCHM-02 made observable: append-only entities accumulate, not replace."""
    first = (await client.get("/api/skeleton/schema-status")).json()
    first_counts = {row["entity"]: row["count"] for row in first["entities"]}

    await client.post("/api/skeleton/chain")

    second = (await client.get("/api/skeleton/schema-status")).json()
    second_counts = {row["entity"]: row["count"] for row in second["entities"]}

    await client.post("/api/skeleton/chain")

    third = (await client.get("/api/skeleton/schema-status")).json()
    third_counts = {row["entity"]: row["count"] for row in third["entities"]}

    for entity in _APPEND_ONLY_ENTITIES:
        assert second_counts[entity] > first_counts[entity], entity
        assert third_counts[entity] > second_counts[entity], entity


@pytest.mark.postgis
async def test_status_patch_persists_and_is_reflected_on_get(client):
    seed_response = await client.post("/api/skeleton/chain")
    report_id = seed_response.json()["report_id"]

    patch_response = await client.patch(
        f"/api/skeleton/reports/{report_id}/status",
        json={"status": "corroborated"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "corroborated"

    list_response = await client.get("/api/skeleton/reports")
    assert list_response.status_code == 200
    matching = [row for row in list_response.json() if row["id"] == report_id]
    assert matching, "seeded report should still be listed"
    assert matching[0]["status"] == "corroborated"


@pytest.mark.postgis
async def test_status_patch_against_unknown_report_returns_404(client):
    response = await client.patch(
        f"/api/skeleton/reports/{uuid.uuid4()}/status",
        json={"status": "corroborated"},
    )
    assert response.status_code == 404
