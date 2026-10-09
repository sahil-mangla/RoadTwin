"""SPAT-01..03 building blocks that need no database."""

import uuid

import pytest

from backend.services.spatial.clustering import GeoItem, assign_duplicates, dbscan_labels
from backend.services.spatial.geo import haversine_m, point_to_segment_m, principal_axis_endpoints
from backend.services.spatial.reconcile import ExistingSegment, reconcile

LAT, LON = 12.9716, 77.5946
M_PER_DEG_LAT = 111_195.0


def at(north_m: float, east_m: float = 0.0):
    import math

    return (LAT + north_m / M_PER_DEG_LAT, LON + east_m / (M_PER_DEG_LAT * math.cos(math.radians(LAT))))


def item(north_m, order, east_m=0.0):
    return GeoItem(uuid.uuid4(), at(north_m, east_m), (order,))


def test_haversine_known_distance():
    assert haversine_m(at(0), at(100)) == pytest.approx(100, rel=0.01)


def test_dbscan_groups_by_radius():
    labels = dbscan_labels([at(0), at(10), at(500)], eps_meters=15)
    assert labels[0] == labels[1] != labels[2]


def test_two_reports_of_same_damage_become_duplicates():
    a, b = item(0, 1), item(5, 2)
    mapping = assign_duplicates([a, b], radius_meters=15)
    assert mapping[a.id] == a.id  # oldest stays canonical
    assert mapping[b.id] == a.id


def test_chain_of_reports_is_not_collapsed_into_one_damage():
    # Spaced 12 m apart: DBSCAN chains them, but only neighbours of a
    # canonical within 15 m may be duplicates.
    chain = [item(12 * i, i) for i in range(6)]
    mapping = assign_duplicates(chain, radius_meters=15)
    assert len(set(mapping.values())) > 1


def test_oldest_report_stays_canonical_when_newer_arrives():
    old, new = item(0, 1), item(3, 2)
    first = assign_duplicates([old], 15)
    second = assign_duplicates([old, new], 15)
    assert first[old.id] == second[old.id] == old.id


def test_principal_axis_endpoints_span_the_cluster():
    pts = [at(0), at(20), at(40), at(60), at(80, 2)]
    start, end = principal_axis_endpoints(pts)
    assert haversine_m(start, end) == pytest.approx(80, rel=0.05)


def test_single_point_endpoints_coincide():
    start, end = principal_axis_endpoints([at(0)])
    assert start == end


def test_point_to_segment_distance():
    assert point_to_segment_m(at(50, 10), at(0), at(100)) == pytest.approx(10, abs=0.5)
    assert point_to_segment_m(at(130), at(0), at(100)) == pytest.approx(30, abs=0.5)


def test_reconcile_keeps_segment_with_most_votes_and_new_for_other_half():
    seg = uuid.uuid4()
    big = [(uuid.uuid4(), at(0), seg), (uuid.uuid4(), at(10), seg), (uuid.uuid4(), at(20), seg)]
    small = [(uuid.uuid4(), at(400), seg)]
    result = reconcile([small, big], [ExistingSegment(seg, at(0), at(400))], 50)
    assert result == [None, seg]


def test_reconcile_merge_keeps_one_identity():
    a, b = uuid.uuid4(), uuid.uuid4()
    merged = [(uuid.uuid4(), at(0), a), (uuid.uuid4(), at(10), a), (uuid.uuid4(), at(20), b)]
    result = reconcile([merged], [ExistingSegment(a, at(0), at(10)), ExistingSegment(b, at(20), at(30))], 50)
    assert result == [a]


def test_reconcile_adopts_nearby_unclaimed_segment_for_new_cluster():
    seg = uuid.uuid4()
    new_cluster = [(uuid.uuid4(), at(20), None)]
    assert reconcile([new_cluster], [ExistingSegment(seg, at(0), at(10))], 50) == [seg]


def test_reconcile_does_not_adopt_far_segment():
    seg = uuid.uuid4()
    new_cluster = [(uuid.uuid4(), at(500), None)]
    assert reconcile([new_cluster], [ExistingSegment(seg, at(0), at(10))], 50) == [None]
