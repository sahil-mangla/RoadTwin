"""PRIO-01/02: the priority score and its explanation."""

import datetime as dt

import pytest

from backend.services.maintenance.priority import PriorityInputs, compute_priority, urgency_for

NOW = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)


def inputs(**overrides):
    base = dict(
        severity_burden=60.0, deterioration_rate=-0.5, density_burden=40.0, evidence_burden=80.0,
        health_score=55.0, traffic_exposure=None, road_type=None,
        near_vulnerable_location=None, last_repaired_at=None, dominant_damage_type="D40",
    )
    base.update(overrides)
    return PriorityInputs(**base)


def test_worse_road_ranks_higher():
    mild = compute_priority(inputs(severity_burden=10, deterioration_rate=0.0, density_burden=5), NOW)
    bad = compute_priority(inputs(severity_burden=90, deterioration_rate=-1.0, density_burden=80), NOW)
    assert bad.score > mild.score


def test_missing_external_inputs_are_left_out_not_required():
    result = compute_priority(inputs(), NOW)
    assert result.factors["traffic"] is None and "traffic" not in result.weights
    assert sum(result.weights.values()) == pytest.approx(1.0)
    assert "No data for:" in result.explanation and "traffic exposure" in result.explanation


def test_external_inputs_raise_priority_when_present():
    base = compute_priority(inputs(), NOW).score
    busy = compute_priority(
        inputs(traffic_exposure=1.0, road_type="arterial", near_vulnerable_location=True), NOW
    ).score
    assert busy > base


def test_unknown_deterioration_is_excluded_and_explained():
    result = compute_priority(inputs(deterioration_rate=None), NOW)
    assert "deterioration" not in result.weights
    assert "insufficient history" in result.explanation


def test_improving_road_gets_no_deterioration_points():
    assert compute_priority(inputs(deterioration_rate=0.4), NOW).contributions["deterioration"] == 0


def test_contributions_sum_to_score_and_drivers_are_named():
    result = compute_priority(inputs(), NOW)
    assert sum(result.contributions.values()) == pytest.approx(result.score)
    assert "Main drivers:" in result.explanation and "damage severity" in result.explanation
    assert "Provisional" in result.explanation


def test_repair_recency_grows_with_time_since_repair():
    recent = compute_priority(inputs(last_repaired_at=NOW - dt.timedelta(days=10)), NOW)
    old = compute_priority(inputs(last_repaired_at=NOW - dt.timedelta(days=400)), NOW)
    assert old.factors["repair_recency"] == 1.0 > recent.factors["repair_recency"]


def test_no_damage_means_low_priority_and_monitoring():
    result = compute_priority(
        inputs(severity_burden=0, deterioration_rate=None, density_burden=0, evidence_burden=0, health_score=100),
        NOW,
    )
    assert result.score == 0 and result.urgency == "low"
    assert result.recommended_action.startswith("Monitor")


def test_action_names_the_repair_method_for_the_dominant_damage():
    result = compute_priority(inputs(severity_burden=100, density_burden=100, deterioration_rate=-2), NOW)
    assert result.urgency in {"immediate", "high"}
    assert "pothole patching" in result.recommended_action


@pytest.mark.parametrize("score,label", [(85, "immediate"), (70, "immediate"), (55, "high"), (35, "medium"), (5, "low")])
def test_urgency_bands(score, label):
    assert urgency_for(score) == label
