"""DBSCAN-based spatial grouping (SPAT-01, SPAT-02).

`min_samples=1` makes every point belong to some cluster (no "noise"):
a lone report is a valid one-report group or segment.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import DBSCAN

from backend.services.spatial.geo import EARTH_RADIUS_M, Point, haversine_m


@dataclass(frozen=True)
class GeoItem:
    id: uuid.UUID
    point: Point  # (lat, lon)
    order_key: tuple  # canonical choice: smallest wins (created_at, id)


def dbscan_labels(points: list[Point], eps_meters: float) -> list[int]:
    if not points:
        return []
    coords = np.radians(np.asarray(points, dtype=float))
    model = DBSCAN(
        eps=eps_meters / EARTH_RADIUS_M, min_samples=1, metric="haversine", algorithm="ball_tree"
    )
    return [int(label) for label in model.fit_predict(coords)]


def group_items(items: list[GeoItem], eps_meters: float) -> list[list[GeoItem]]:
    labels = dbscan_labels([i.point for i in items], eps_meters)
    groups: dict[int, list[GeoItem]] = {}
    for item, label in zip(items, labels):
        groups.setdefault(label, []).append(item)
    return list(groups.values())


def assign_duplicates(items: list[GeoItem], radius_meters: float) -> dict[uuid.UUID, uuid.UUID]:
    """Maps every item id to its canonical item id (canonicals map to themselves).

    DBSCAN finds the groups of near-coincident reports; inside a group a
    greedy pass, oldest first, makes an item a duplicate only if it lies
    within `radius_meters` of an existing canonical. That stops DBSCAN's
    chaining from merging a whole line of reports spaced just under the
    radius apart into one "damage", and keeps the oldest report canonical
    as newer ones arrive.
    """
    canonical_of: dict[uuid.UUID, uuid.UUID] = {}
    for group in group_items(items, radius_meters):
        canonicals: list[GeoItem] = []
        for item in sorted(group, key=lambda i: i.order_key):
            home = min(
                (c for c in canonicals if haversine_m(c.point, item.point) <= radius_meters),
                key=lambda c: haversine_m(c.point, item.point),
                default=None,
            )
            if home is None:
                canonicals.append(item)
                canonical_of[item.id] = item.id
            else:
                canonical_of[item.id] = home.id
    return canonical_of
