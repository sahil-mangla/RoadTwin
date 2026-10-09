"""Transparent health-score forecasts at 30/60/90 days (FCST-01).

Method escalation, per the project's no-black-box rule:

* fewer than `forecast_holt_min_points` health points: ordinary
  least-squares line through the history, extended forward;
* otherwise: Holt's linear exponential smoothing with a *damped* trend on
  a daily series (statsmodels), so the trend flattens over the horizon
  instead of running off the 0-100 scale.

Forecasts are clamped to [0, 100]. Failure probability is the chance the
forecast falls below the failure threshold, assuming normally distributed
error with spread taken from the fit's own residuals and widened with the
horizon. All of this is provisional and is explained in plain language on
every forecast. Pure functions, no I/O.
"""

from __future__ import annotations

import datetime as dt
import math
import warnings
from dataclasses import dataclass

import numpy as np

from backend.core.config import Settings, settings as default_settings
from backend.services.intelligence.deterioration import HealthPoint, span_in_days

HORIZONS_DAYS = (30, 60, 90)
METHOD_LINEAR = "linear-ols-v1"
METHOD_HOLT = "holt-damped-v1"


@dataclass(frozen=True)
class HorizonForecast:
    horizon_days: int
    predicted_health_score: float
    failure_probability: float
    confidence: float
    method: str
    explanation: str


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def _daily_series(points: list[HealthPoint]) -> np.ndarray:
    """Step-interpolated daily series: each day carries the latest reading so far."""
    ordered = sorted(points)
    start = ordered[0][0].date()
    days = (ordered[-1][0].date() - start).days + 1
    series = np.empty(days)
    idx, current = 0, ordered[0][1]
    for d in range(days):
        day = start + dt.timedelta(days=d)
        while idx < len(ordered) and ordered[idx][0].date() <= day:
            current = ordered[idx][1]
            idx += 1
        series[d] = current
    return series


def _linear(points: list[HealthPoint], horizons: tuple[int, ...]) -> tuple[dict[int, float], float]:
    ordered = sorted(points)
    t0 = ordered[0][0]
    x = np.array([(t - t0).total_seconds() / 86400 for t, _ in ordered])
    y = np.array([h for _, h in ordered])
    slope, intercept = np.polyfit(x, y, 1)
    rmse = float(np.sqrt(np.mean((y - (slope * x + intercept)) ** 2)))
    return {h: float(slope * (x[-1] + h) + intercept) for h in horizons}, rmse


def _holt(points: list[HealthPoint], horizons: tuple[int, ...]) -> tuple[dict[int, float], float]:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    series = _daily_series(points)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(
            series, trend="add", damped_trend=True, initialization_method="estimated"
        ).fit()
        ahead = np.asarray(fit.forecast(max(horizons)))
    rmse = float(np.sqrt(np.mean((series - np.asarray(fit.fittedvalues)) ** 2)))
    return {h: float(ahead[h - 1]) for h in horizons}, rmse


def forecast_health(
    points: list[HealthPoint],
    cfg: Settings = default_settings,
    horizons: tuple[int, ...] = HORIZONS_DAYS,
) -> list[HorizonForecast]:
    """Caller must have passed the minimum-data gate (FCST-02)."""
    if len(points) < 2:
        raise ValueError("at least two health points are required")
    if len(points) >= cfg.forecast_holt_min_points:
        raw, rmse = _holt(points, horizons)
        method = METHOD_HOLT
        how = (
            f"Holt's linear exponential smoothing with a damped trend, fitted to "
            f"{len(points)} health measurements resampled to a daily series; the trend "
            f"flattens over the horizon rather than continuing forever."
        )
    else:
        raw, rmse = _linear(points, horizons)
        method = METHOD_LINEAR
        how = (
            f"a straight line fitted by least squares through {len(points)} health "
            f"measurements, extended forward (too little history for smoothing)."
        )

    span = span_in_days(points)
    results = []
    for h in horizons:
        predicted = _clamp(raw[h])
        sigma = max(rmse, 2.0) * math.sqrt(1 + h / 30)
        failure = _normal_cdf((cfg.forecast_failure_health_threshold - predicted) / sigma)
        confidence = _clamp(1 - rmse / 10, 0.0, 1.0) * (span / (span + h))
        results.append(
            HorizonForecast(
                horizon_days=h,
                predicted_health_score=predicted,
                failure_probability=_clamp(failure, 0.0, 1.0),
                confidence=confidence,
                method=method,
                explanation=(
                    f"Predicted health {predicted:.1f} in {h} days using {how} "
                    f"The fit's typical error is {rmse:.1f} points, so confidence is "
                    f"{confidence:.0%}. 'Failure probability' is the estimated chance health "
                    f"falls below {cfg.forecast_failure_health_threshold:g}. "
                    f"Provisional baseline, not a validated model."
                ),
            )
        )
    return results
