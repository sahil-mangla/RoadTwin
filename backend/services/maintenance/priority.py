"""Maintenance priority score with a plain-language explanation (PRIO-01, PRIO-02).

    Priority = 100 * sum(w_i * f_i) / sum(w_i)   over the factors that have data

Eight factors, each 0..1: severity, deterioration, damage density, evidence
confidence, traffic exposure, road importance, vulnerable-location
proximity, repair recency. The last four are external enhancement inputs:
when one is unknown it is left out and the remaining weights are
renormalised, so the score never depends on data that may not exist. The
explanation says which factors drove the ranking and which were missing.

All weights and mappings are PROVISIONAL, tunable settings. Pure functions.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from backend.core.config import Settings, settings as default_settings

FACTOR_LABELS = {
    "severity": "damage severity",
    "deterioration": "rate of deterioration",
    "density": "damage density",
    "evidence": "strength of evidence",
    "traffic": "traffic exposure",
    "importance": "road importance",
    "vulnerable": "nearby vulnerable locations",
    "repair_recency": "time since last repair",
}

ROAD_IMPORTANCE = {
    "highway": 1.0, "motorway": 1.0, "arterial": 0.85, "primary": 0.85,
    "collector": 0.6, "secondary": 0.6, "local": 0.3, "residential": 0.3,
}

URGENCY_BANDS = ((70.0, "immediate"), (50.0, "high"), (30.0, "medium"), (0.0, "low"))

ACTION_BY_URGENCY = {
    "immediate": "Dispatch a repair crew within 7 days",
    "high": "Schedule repair within 30 days",
    "medium": "Add to the next maintenance cycle and keep monitoring",
    "low": "Monitor; no repair scheduled",
}

ACTION_BY_DAMAGE = {
    "D40": "pothole patching",
    "D20": "resurfacing or overlay of the cracked area",
    "D00": "crack sealing",
    "D10": "crack sealing",
}


@dataclass(frozen=True)
class PriorityInputs:
    severity_burden: float | None          # 0..100, from RoadHealth
    deterioration_rate: float | None       # health points/day; None = insufficient data
    density_burden: float | None           # 0..100
    evidence_burden: float | None          # 0..100 (mean evidence of the damage)
    health_score: float | None
    traffic_exposure: float | None         # 0..1
    road_type: str | None
    near_vulnerable_location: bool | None
    last_repaired_at: dt.datetime | None
    dominant_damage_type: str | None


@dataclass(frozen=True)
class PriorityResult:
    score: float
    urgency: str
    recommended_action: str
    explanation: str
    factors: dict[str, float | None]       # None = no data, left out
    weights: dict[str, float]              # renormalised over present factors
    contributions: dict[str, float]        # points of the 0..100 score

    def as_record(self) -> dict:
        return {
            "method": "weighted-factors-v1",
            "provisional": True,
            "score": round(self.score, 2),
            "factors": {k: (None if v is None else round(v, 4)) for k, v in self.factors.items()},
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "contributions": {k: round(v, 2) for k, v in self.contributions.items()},
        }


def _unit(x: float) -> float:
    return max(0.0, min(1.0, x))


def urgency_for(score: float) -> str:
    for lower, label in URGENCY_BANDS:
        if score >= lower:
            return label
    return "low"


def _factors(inp: PriorityInputs, now: dt.datetime, cfg: Settings) -> dict[str, float | None]:
    return {
        "severity": None if inp.severity_burden is None else _unit(inp.severity_burden / 100),
        "deterioration": (
            None
            if inp.deterioration_rate is None
            else _unit(-inp.deterioration_rate / cfg.priority_deterioration_saturation_per_day)
        ),
        "density": None if inp.density_burden is None else _unit(inp.density_burden / 100),
        "evidence": None if inp.evidence_burden is None else _unit(inp.evidence_burden / 100),
        "traffic": None if inp.traffic_exposure is None else _unit(inp.traffic_exposure),
        "importance": ROAD_IMPORTANCE.get((inp.road_type or "").strip().lower()),
        "vulnerable": (
            None if inp.near_vulnerable_location is None else float(inp.near_vulnerable_location)
        ),
        "repair_recency": (
            None
            if inp.last_repaired_at is None
            else _unit(
                (now - inp.last_repaired_at).total_seconds() / 86400
                / cfg.priority_repair_recency_saturation_days
            )
        ),
    }


def compute_priority(
    inp: PriorityInputs, now: dt.datetime, cfg: Settings = default_settings
) -> PriorityResult:
    raw_weights = {
        "severity": cfg.priority_weight_severity,
        "deterioration": cfg.priority_weight_deterioration,
        "density": cfg.priority_weight_density,
        "evidence": cfg.priority_weight_evidence,
        "traffic": cfg.priority_weight_traffic,
        "importance": cfg.priority_weight_importance,
        "vulnerable": cfg.priority_weight_vulnerable,
        "repair_recency": cfg.priority_weight_repair_recency,
    }
    factors = _factors(inp, now, cfg)
    present = {k: w for k, w in raw_weights.items() if factors[k] is not None and w > 0}
    total = sum(present.values())
    weights = {k: w / total for k, w in present.items()} if total > 0 else {}
    contributions = {k: 100 * weights[k] * factors[k] for k in weights}
    score = max(0.0, min(100.0, sum(contributions.values())))
    urgency = urgency_for(score)

    action = ACTION_BY_URGENCY[urgency]
    method = ACTION_BY_DAMAGE.get(inp.dominant_damage_type or "")
    if method and urgency != "low":
        action = f"{action}: {method}"

    return PriorityResult(
        score=score,
        urgency=urgency,
        recommended_action=action,
        explanation=_explain(score, urgency, factors, contributions, inp),
        factors=factors,
        weights=weights,
        contributions=contributions,
    )


def _explain(score, urgency, factors, contributions, inp) -> str:
    ranked = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)
    drivers = [
        f"{FACTOR_LABELS[k]} ({v:.0f} pts)" for k, v in ranked if v >= 1.0
    ][:3]
    parts = [f"Priority {score:.0f}/100 ({urgency})."]
    if drivers:
        parts.append("Main drivers: " + ", ".join(drivers) + ".")
    else:
        parts.append("No factor currently adds meaningfully to the priority.")
    if inp.health_score is not None:
        parts.append(f"Current health is {inp.health_score:.0f}/100.")
    if inp.deterioration_rate is None:
        parts.append("Deterioration rate is not yet known (insufficient history), so it is left out.")
    elif inp.deterioration_rate < 0:
        parts.append(f"Health is falling about {-inp.deterioration_rate:.2f} points per day.")
    missing = [FACTOR_LABELS[k] for k, v in factors.items() if v is None and k != "deterioration"]
    if missing:
        parts.append("No data for: " + ", ".join(missing) + "; these were left out of the score.")
    parts.append("Provisional, tunable score -- not a validated engineering assessment.")
    return " ".join(parts)
