"""HLTH-02..04 and FCST-01..02: the pure math."""

import datetime as dt

import pytest

from backend.core.config import Settings
from backend.services.intelligence.deterioration import (
    check_history,
    deterioration_rate,
    trend_label,
)
from backend.services.intelligence.forecast import (
    METHOD_HOLT,
    METHOD_LINEAR,
    forecast_health,
)
from backend.services.intelligence.health import Damage, compute_health, interpretation_band

NOW = dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc)


def pts(values, every_days=5):
    return [(NOW + dt.timedelta(days=i * every_days), v) for i, v in enumerate(values)]


def damage(sev="moderate", ev=1.0, days_ago=100):
    return Damage(sev, ev, NOW - dt.timedelta(days=days_ago))


# --- HLTH-02 ---------------------------------------------------------------

@pytest.mark.parametrize(
    "score,band",
    [(100, "Excellent"), (80, "Excellent"), (79.9, "Good"), (60, "Good"), (59, "Poor"),
     (40, "Poor"), (39, "Critical"), (20, "Critical"), (19, "Severely degraded"), (0, "Severely degraded")],
)
def test_interpretation_bands(score, band):
    assert interpretation_band(score) == band


def test_no_damage_is_perfect_health():
    result = compute_health([], 100, NOW)
    assert result.score == 100 and result.band == "Excellent"


def test_more_and_worse_damage_lowers_health():
    one = compute_health([damage("low")], 100, NOW).score
    worse = compute_health([damage("critical")], 100, NOW).score
    many = compute_health([damage("critical")] * 4, 100, NOW).score
    assert 100 > one > worse > many >= 0


def test_unproven_damage_hurts_less_than_confirmed_damage():
    weak = compute_health([damage("critical", ev=0.2)], 100, NOW).score
    strong = compute_health([damage("critical", ev=1.0)], 100, NOW).score
    assert weak > strong


def test_recent_damage_lowers_health_more_than_old_damage():
    old = compute_health([damage(days_ago=200)], 100, NOW)
    new = compute_health([damage(days_ago=3)], 100, NOW)
    assert new.score < old.score
    assert new.burdens["temporal"] > old.burdens["temporal"] == 0


def test_same_damage_on_a_shorter_road_is_denser():
    short = compute_health([damage()] * 2, 50, NOW)
    long = compute_health([damage()] * 2, 500, NOW)
    assert short.burdens["density"] > long.burdens["density"]


def test_score_stays_within_bounds_and_burdens_are_reported():
    result = compute_health([damage("critical", days_ago=1)] * 50, 10, NOW)
    assert 0 <= result.score <= 100
    assert set(result.burdens) == {"severity", "density", "temporal", "evidence"}
    assert all(0 <= b <= 100 for b in result.burdens.values())


# --- HLTH-03 / HLTH-04 -------------------------------------------------------

def test_rate_matches_the_spec_formula_for_two_points():
    two = [(NOW, 82.0), (NOW + dt.timedelta(days=15), 73.0)]
    assert deterioration_rate(two) == pytest.approx((73 - 82) / 15)


def test_rate_for_the_spec_example_is_rapid_deterioration():
    history = [(NOW + dt.timedelta(days=d), h) for d, h in [(1, 82), (15, 73), (30, 61), (45, 48)]]
    rate = deterioration_rate(history)
    assert rate == pytest.approx(-0.77, abs=0.03)
    assert trend_label(rate) == "rapidly deteriorating"


def test_stable_and_improving_labels():
    assert trend_label(0.0) == "stable"
    assert trend_label(-0.05) == "stable"
    assert trend_label(0.5) == "improving"
    assert trend_label(-0.2) == "deteriorating"


def test_gate_withholds_with_too_few_points_or_too_short_a_span():
    gate = check_history(pts([80, 78]), observation_reports=5)
    assert not gate.sufficient
    assert any("measurements" in r for r in gate.reasons)
    assert any("spanning" in r for r in gate.reasons)


def test_gate_withholds_with_too_few_observations():
    gate = check_history(pts([80, 78, 75, 70], every_days=10), observation_reports=1)
    assert not gate.sufficient and len(gate.reasons) == 1


def test_gate_passes_with_enough_of_everything():
    assert check_history(pts([80, 78, 75, 70], every_days=10), observation_reports=3).sufficient


def test_gate_thresholds_are_configurable():
    cfg = Settings(history_min_points=2, history_min_days=1, history_min_observation_reports=1)
    assert check_history(pts([80, 78], every_days=2), 1, cfg).sufficient


# --- FCST-01 -----------------------------------------------------------------

def test_short_history_uses_the_linear_baseline_and_continues_the_trend():
    history = pts([90, 85, 80, 75], every_days=10)  # -0.5 / day
    forecasts = {f.horizon_days: f for f in forecast_health(history)}
    assert set(forecasts) == {30, 60, 90}
    assert all(f.method == METHOD_LINEAR for f in forecasts.values())
    assert forecasts[30].predicted_health_score == pytest.approx(60, abs=0.5)
    assert forecasts[60].predicted_health_score < forecasts[30].predicted_health_score


def test_long_history_uses_damped_holt_and_stays_on_the_scale():
    history = pts([95, 90, 84, 77, 70, 62, 54], every_days=5)
    forecasts = forecast_health(history)
    assert all(f.method == METHOD_HOLT for f in forecasts)
    assert all(0 <= f.predicted_health_score <= 100 for f in forecasts)
    scores = [f.predicted_health_score for f in forecasts]
    assert scores == sorted(scores, reverse=True)  # still heading down, never past 0
    assert scores[0] < 54


def test_steep_decline_is_clamped_at_zero():
    history = pts([40, 30, 20, 10], every_days=10)
    assert forecast_health(history)[-1].predicted_health_score == 0


def test_stable_road_forecasts_stable_with_low_failure_risk():
    forecasts = forecast_health(pts([85, 85, 85, 85, 85, 85], every_days=5))
    assert all(abs(f.predicted_health_score - 85) < 1 for f in forecasts)
    assert all(f.failure_probability < 0.01 for f in forecasts)


def test_failure_probability_rises_for_a_road_heading_to_failure():
    declining = forecast_health(pts([60, 55, 50, 45], every_days=10))
    stable = forecast_health(pts([85, 85, 85, 85], every_days=10))
    assert declining[-1].failure_probability > stable[-1].failure_probability
    assert all(0 <= f.failure_probability <= 1 for f in declining)


def test_every_forecast_carries_a_plain_language_explanation():
    for f in forecast_health(pts([90, 85, 80, 75], every_days=10)):
        assert "least squares" in f.explanation and "Provisional" in f.explanation
        assert 0 <= f.confidence <= 1


def test_longer_horizons_are_less_confident():
    confidences = [f.confidence for f in forecast_health(pts([90, 86, 83, 79], every_days=10))]
    assert confidences == sorted(confidences, reverse=True)
