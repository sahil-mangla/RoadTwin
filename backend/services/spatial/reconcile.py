"""Matches freshly computed clusters onto existing segment identities (SPAT-03).

Pure functions: no I/O, so the identity rules are unit-testable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from backend.services.spatial.geo import Point, point_to_segment_m


@dataclass(frozen=True)
class ExistingSegment:
    id: uuid.UUID
    start: Point
    end: Point


def reconcile(
    clusters: list[list[tuple[uuid.UUID, Point, uuid.UUID | None]]],
    segments: list[ExistingSegment],
    reconcile_distance_meters: float,
) -> list[uuid.UUID | None]:
    """For each cluster, the existing segment id it keeps, or None for a new one.

    Each cluster member is (report_id, point, report's current segment id).

    1. Vote: a cluster inherits the segment most of its reports already
       belong to. Biggest overlaps are settled first, each segment is
       claimed at most once, so a split keeps the id on the larger half
       and a merge keeps the id of the larger side.
    2. Proximity: a cluster still unmatched adopts the nearest *unclaimed*
       segment within `reconcile_distance_meters`, covering a segment
       whose old reports no longer qualify.
    """
    result: list[uuid.UUID | None] = [None] * len(clusters)
    claimed: set[uuid.UUID] = set()

    votes: list[tuple[int, int, uuid.UUID]] = []  # (-count, cluster_idx, segment_id)
    for idx, members in enumerate(clusters):
        counts: dict[uuid.UUID, int] = {}
        for _, _, seg_id in members:
            if seg_id is not None:
                counts[seg_id] = counts.get(seg_id, 0) + 1
        votes.extend((-n, idx, seg_id) for seg_id, n in counts.items())
    for _, idx, seg_id in sorted(votes, key=lambda v: (v[0], v[1], str(v[2]))):
        if result[idx] is None and seg_id not in claimed:
            result[idx] = seg_id
            claimed.add(seg_id)

    for idx, members in enumerate(clusters):
        if result[idx] is not None:
            continue
        best: tuple[float, uuid.UUID] | None = None
        for seg in segments:
            if seg.id in claimed:
                continue
            dist = min(point_to_segment_m(p, seg.start, seg.end) for _, p, _ in members)
            if dist <= reconcile_distance_meters and (best is None or dist < best[0]):
                best = (dist, seg.id)
        if best is not None:
            result[idx] = best[1]
            claimed.add(best[1])
    return result
