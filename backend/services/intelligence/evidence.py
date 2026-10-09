"""Multi-signal evidence score for one detection (EVID-01..03).

YOLO confidence says how sure the model is about a picture, not whether a
road defect exists. The score therefore blends five signals, and the model
confidence carries only part of the weight: a lone report of a
high-confidence detection cannot reach full evidence, however sure the
model is. Every component is returned alongside the total so the score can
be logged, stored and explained.

Pure functions, no I/O.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from backend.core.config import Settings, settings as default_settings
from backend.services.spatial.geo import Point, haversine_m

COMPONENTS = (
    "ml_confidence",
    "observation_count",
    "spatial_agreement",
    "temporal_consistency",
    "community_validation",
)


@dataclass(frozen=True)
class IndependentReport:
    """One report per distinct identity in a damage group."""

    point: Point
    observed_at: dt.datetime


@dataclass(frozen=True)
class EvidenceInputs:
    ml_confidence: float
    reporters: list[IndependentReport]
    corroborating_voters: int


@dataclass(frozen=True)
class EvidenceScore:
    score: float
    components: dict[str, float]      # each signal, 0..1
    weights: dict[str, float]         # normalised weights actually applied
    contributions: dict[str, float]   # weight * component; sums to `score`
    method: str = "weighted-sum-v1"

    def as_record(self) -> dict:
        return {
            "method": self.method,
            "score": round(self.score, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
        }


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def normalised_weights(cfg: Settings) -> dict[str, float]:
    raw = {
        "ml_confidence": cfg.evidence_weight_ml_confidence,
        "observation_count": cfg.evidence_weight_observation_count,
        "spatial_agreement": cfg.evidence_weight_spatial_agreement,
        "temporal_consistency": cfg.evidence_weight_temporal_consistency,
        "community_validation": cfg.evidence_weight_community_validation,
    }
    total = sum(raw.values())
    if total <= 0 or any(v < 0 for v in raw.values()):
        raise ValueError("evidence weights must be non-negative with a positive sum")
    return {k: v / total for k, v in raw.items()}


def observation_count_signal(n: int, saturation: int) -> float:
    """0 for a lone reporter, 1 once `saturation` independent reporters agree."""
    if n <= 1 or saturation <= 1:
        return 0.0
    return _clamp((n - 1) / (saturation - 1))


def spatial_agreement_signal(points: list[Point], radius_m: float) -> float:
    """How tightly independent reporters' locations coincide (0 for a lone report)."""
    if len(points) < 2 or radius_m <= 0:
        return 0.0
    lat = sum(p[0] for p in points) / len(points)
    lon = sum(p[1] for p in points) / len(points)
    mean_dist = sum(haversine_m((lat, lon), p) for p in points) / len(points)
    return _clamp(1.0 - mean_dist / radius_m)


def temporal_consistency_signal(times: list[dt.datetime], saturation_days: float) -> float:
    """Damage seen again after time has passed, not just at one moment."""
    if len(times) < 2 or saturation_days <= 0:
        return 0.0
    span_days = (max(times) - min(times)).total_seconds() / 86400
    return _clamp(span_days / saturation_days)


def community_signal(voters: int, saturation: int) -> float:
    if voters <= 0 or saturation <= 0:
        return 0.0
    return _clamp(voters / saturation)


def compute_evidence(inputs: EvidenceInputs, cfg: Settings = default_settings) -> EvidenceScore:
    components = {
        "ml_confidence": _clamp(inputs.ml_confidence),
        "observation_count": observation_count_signal(
            len(inputs.reporters), cfg.evidence_count_saturation
        ),
        "spatial_agreement": spatial_agreement_signal(
            [r.point for r in inputs.reporters], cfg.duplicate_radius_meters
        ),
        "temporal_consistency": temporal_consistency_signal(
            [r.observed_at for r in inputs.reporters], cfg.evidence_temporal_saturation_days
        ),
        "community_validation": community_signal(
            inputs.corroborating_voters, cfg.evidence_community_saturation
        ),
    }
    weights = normalised_weights(cfg)
    contributions = {k: weights[k] * components[k] for k in COMPONENTS}
    return EvidenceScore(
        score=_clamp(math.fsum(contributions.values())),
        components=components,
        weights=weights,
        contributions=contributions,
    )


def format_log(label: str, result: EvidenceScore) -> str:
    parts = " ".join(f"{k}={result.contributions[k]:.3f}" for k in COMPONENTS)
    return f"evidence {label} score={result.score:.3f} | {parts}"
