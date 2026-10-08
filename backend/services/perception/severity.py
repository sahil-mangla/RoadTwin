"""Severity from bounding-box features (PERC-02).

Severity is derived from how much of the frame a defect occupies and what
kind of defect it is -- never from the model's confidence, which says how
sure the model is, not how bad the road is.

The multipliers and band edges are PROVISIONAL, tunable starting values
(the project labels all scores provisional until validated): cracks are
thin, so their boxes under-represent their impact and get a larger
multiplier than potholes, whose boxes are compact and dense.
"""

# RDD2022 class codes. Unknown codes fall back to DEFAULT_MULTIPLIER.
DAMAGE_TYPE_MULTIPLIER: dict[str, float] = {
    "D00": 3.0,  # longitudinal crack
    "D10": 3.0,  # transverse crack
    "D20": 1.5,  # alligator crack
    "D40": 1.0,  # pothole
}
DEFAULT_MULTIPLIER = 2.0

# Some RDD2022 checkpoints name their classes in words instead of codes.
# Detections are stored under the canonical code either way.
CLASS_NAME_TO_CODE: dict[str, str] = {
    "longitudinal crack": "D00",
    "transverse crack": "D10",
    "alligator crack": "D20",
    "pothole": "D40",
    "potholes": "D40",
}


def canonical_damage_type(name: str) -> str:
    """Maps a model class name to its RDD2022 code; unknown names pass through."""
    return CLASS_NAME_TO_CODE.get(name.strip().lower(), name)

# Upper edges (exclusive) of the effective-area bands, ascending.
SEVERITY_BANDS: tuple[tuple[float, str], ...] = (
    (0.02, "low"),
    (0.08, "moderate"),
    (0.20, "high"),
)
TOP_SEVERITY = "critical"


def bbox_area_ratio(x1: float, y1: float, x2: float, y2: float, width: int, height: int) -> float:
    """Box area as a fraction of the image area, clamped to [0, 1]."""
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    box_w = max(0.0, min(x2, width) - max(x1, 0.0))
    box_h = max(0.0, min(y2, height) - max(y1, 0.0))
    return min(1.0, (box_w * box_h) / (width * height))


def derive_severity(damage_type: str, area_ratio: float) -> str:
    effective = area_ratio * DAMAGE_TYPE_MULTIPLIER.get(damage_type, DEFAULT_MULTIPLIER)
    for upper, label in SEVERITY_BANDS:
        if effective < upper:
            return label
    return TOP_SEVERITY
