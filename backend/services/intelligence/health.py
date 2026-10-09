"""Road Health Score (HLTH-02).

    RHS = 100 - DamageBurden
    DamageBurden = w1*SeverityBurden + w2*DamageDensity
                 + w3*TemporalDeterioration + w4*EvidenceBurden

Each burden is on a 0-100 scale. All weights and saturation points are
PROVISIONAL, tunable settings, not validated constants. Damages are
distinct physical defects (one per canonical report detection); each
carries an evidence score, so unproven damage weighs less than confirmed
damage. Pure functions, no I/O.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from backend.core.config import Settings, settings as default_settings

SEVERITY_POINTS = {"low": 0.25, "moderate": 0.5, "high": 0.75, "critical": 1.0}
DEFAULT_SEVERITY_POINTS = 0.5

# (inclusive lower bound, label), descending.
BANDS = (
    (80.0, "Excellent"),
    (60.0, "Good"),
    (40.0, "Poor"),
    (20.0, "Critical"),
    (0.0, "Severely degraded"),
)


@dataclass(frozen=True)
class Damage:
    severity: str | None
    evidence: float  # 0..1
    first_observed_at: dt.datetime


@dataclass(frozen=True)
class HealthResult:
    score: float
    band: str
    burdens: dict[str, float]   # each 0..100
    weights: dict[str, float]
    damage_count: int

    def as_record(self) -> dict:
        return {
            "method": "weighted-burden-v1",
            "score": round(self.score, 2),
            "band": self.band,
            "burdens": {k: round(v, 2) for k, v in self.burdens.items()},
            "weights": self.weights,
            "damage_count": self.damage_count,
        }


def interpretation_band(score: float) -> str:
    for lower, label in BANDS:
        if score >= lower:
            return label
    return BANDS[-1][1]


def _cap(x: float) -> float:
    return max(0.0, min(100.0, x))


def compute_health(
    damages: list[Damage],
    length_meters: float | None,
    now: dt.datetime,
    cfg: Settings = default_settings,
) -> HealthResult:
    weights = {
        "severity": cfg.health_weight_severity,
        "density": cfg.health_weight_density,
        "temporal": cfg.health_weight_temporal,
        "evidence": cfg.health_weight_evidence,
    }
    if not damages:
        burdens = {k: 0.0 for k in weights}
        return HealthResult(100.0, interpretation_band(100.0), burdens, weights, 0)

    severity_load = sum(
        SEVERITY_POINTS.get(d.severity or "", DEFAULT_SEVERITY_POINTS) * d.evidence for d in damages
    )
    evidence_count = sum(d.evidence for d in damages)
    length = max(length_meters or 0.0, cfg.health_density_min_length_meters)
    window_start = now - dt.timedelta(days=cfg.health_temporal_window_days)
    recent = sum(d.evidence for d in damages if d.first_observed_at >= window_start)

    burdens = {
        "severity": _cap(100 * severity_load / cfg.health_severity_saturation),
        "density": _cap(
            100 * (evidence_count / length * 100) / cfg.health_density_saturation_per_100m
        ),
        "temporal": _cap(100 * recent / cfg.health_temporal_saturation),
        "evidence": _cap(100 * evidence_count / len(damages)),
    }
    damage_burden = sum(weights[k] * burdens[k] for k in weights)
    score = _cap(100.0 - damage_burden)
    return HealthResult(score, interpretation_band(score), burdens, weights, len(damages))
