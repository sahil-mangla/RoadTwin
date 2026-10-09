"""Collapses overlapping boxes that describe one patch of damage.

A single area of alligator cracking is often boxed several times (one big
box plus boxes over its halves). Counting each as a separate defect would
inflate every downstream count, so same-class boxes that mostly coincide
are reduced to the most confident one.
"""

from __future__ import annotations

from backend.services.perception.detector import RawDetection


def _area(d: RawDetection) -> float:
    return max(0.0, d.x2 - d.x1) * max(0.0, d.y2 - d.y1)


def _intersection(a: RawDetection, b: RawDetection) -> float:
    w = min(a.x2, b.x2) - max(a.x1, b.x1)
    h = min(a.y2, b.y2) - max(a.y1, b.y1)
    return max(0.0, w) * max(0.0, h)


def _redundant(a: RawDetection, b: RawDetection, iou_threshold: float, containment_threshold: float) -> bool:
    inter = _intersection(a, b)
    if inter == 0:
        return False
    smaller = min(_area(a), _area(b))
    union = _area(a) + _area(b) - inter
    return (smaller > 0 and inter / smaller >= containment_threshold) or (
        union > 0 and inter / union >= iou_threshold
    )


def merge_overlapping(
    detections: list[RawDetection],
    iou_threshold: float = 0.5,
    containment_threshold: float = 0.8,
) -> list[RawDetection]:
    """Keeps the most confident box of each overlapping same-class group."""
    kept: list[RawDetection] = []
    for det in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if not any(
            k.damage_type == det.damage_type
            and _redundant(k, det, iou_threshold, containment_threshold)
            for k in kept
        ):
            kept.append(det)
    return kept
