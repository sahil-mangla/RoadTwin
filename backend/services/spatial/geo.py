"""Small-area geometry helpers (metres) for clustering and segment shapes.

Segments are at most a few hundred metres across, so an equirectangular
projection around the points' own centroid is accurate to well under a
metre and far simpler than a full geodesic library.
"""

from __future__ import annotations

import math

import numpy as np

EARTH_RADIUS_M = 6_371_008.8

Point = tuple[float, float]  # (latitude, longitude)


def haversine_m(a: Point, b: Point) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def to_local_meters(points: list[Point], origin: Point | None = None) -> np.ndarray:
    """Projects (lat, lon) points to an (east, north) metre grid around `origin`."""
    origin = origin or (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )
    lat0 = math.radians(origin[0])
    arr = np.asarray(points, dtype=float)
    north = np.radians(arr[:, 0] - origin[0]) * EARTH_RADIUS_M
    east = np.radians(arr[:, 1] - origin[1]) * EARTH_RADIUS_M * math.cos(lat0)
    return np.column_stack([east, north])


def principal_axis_endpoints(points: list[Point]) -> tuple[Point, Point]:
    """The two points furthest apart along the cluster's main direction.

    A one-point cluster yields a zero-length segment (start == end).
    """
    if len(points) == 1:
        return points[0], points[0]
    xy = to_local_meters(points)
    centred = xy - xy.mean(axis=0)
    # First right-singular vector = direction of greatest spread.
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    projection = centred @ vt[0]
    return points[int(np.argmin(projection))], points[int(np.argmax(projection))]


def point_to_segment_m(point: Point, start: Point, end: Point) -> float:
    """Distance in metres from `point` to the segment start-end."""
    xy = to_local_meters([point, start, end], origin=start)
    p, a, b = xy[0], xy[1], xy[2]
    ab = b - a
    denom = float(ab @ ab)
    t = 0.0 if denom == 0 else max(0.0, min(1.0, float((p - a) @ ab) / denom))
    return float(np.linalg.norm(p - (a + t * ab)))
