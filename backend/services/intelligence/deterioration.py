"""Deterioration rate with a minimum-data gate (HLTH-03, HLTH-04).

The rate is the least-squares slope of health score against time, in
health points per day (negative = getting worse). For exactly two points
this is the spec's (H_t2 - H_t1) / elapsed_time; with more history it is
not hostage to a single noisy pair. The same gate guards the forecast
(FCST-02): too little history yields "insufficient data", never a number.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from backend.core.config import Settings, settings as default_settings

HealthPoint = tuple[dt.datetime, float]


@dataclass(frozen=True)
class HistoryGate:
    sufficient: bool
    reasons: list[str]   # what is still missing; empty when sufficient
    points: int
    span_days: float
    observation_reports: int


def span_in_days(points: list[HealthPoint]) -> float:
    if len(points) < 2:
        return 0.0
    times = [t for t, _ in points]
    return (max(times) - min(times)).total_seconds() / 86400


def check_history(
    points: list[HealthPoint], observation_reports: int, cfg: Settings = default_settings
) -> HistoryGate:
    span = span_in_days(points)
    reasons: list[str] = []
    if observation_reports < cfg.history_min_observation_reports:
        reasons.append(
            f"needs reports from at least {cfg.history_min_observation_reports} "
            f"distinct observations (has {observation_reports})"
        )
    if len(points) < cfg.history_min_points:
        reasons.append(
            f"needs at least {cfg.history_min_points} health measurements (has {len(points)})"
        )
    if span < cfg.history_min_days:
        reasons.append(
            f"needs a history spanning at least {cfg.history_min_days:g} days (has {span:.1f})"
        )
    return HistoryGate(not reasons, reasons, len(points), span, observation_reports)


def deterioration_rate(points: list[HealthPoint]) -> float:
    """Least-squares slope, health points per day. Needs >= 2 points."""
    if len(points) < 2:
        raise ValueError("at least two health points are required")
    ordered = sorted(points)
    t0 = ordered[0][0]
    x = np.array([(t - t0).total_seconds() / 86400 for t, _ in ordered])
    y = np.array([h for _, h in ordered])
    if np.ptp(x) == 0:
        raise ValueError("health points share a single timestamp")
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def trend_label(rate: float, cfg: Settings = default_settings) -> str:
    if rate <= cfg.deterioration_rapid_per_day:
        return "rapidly deteriorating"
    if rate <= cfg.deterioration_slow_per_day:
        return "deteriorating"
    if rate >= -cfg.deterioration_slow_per_day:
        return "improving"
    return "stable"
