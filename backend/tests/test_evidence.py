"""EVID-01..03: the evidence score, its weights and its logged breakdown."""

import datetime as dt
import logging

import pytest

from backend.core.config import Settings
from backend.services.intelligence.evidence import (
    COMPONENTS,
    EvidenceInputs,
    IndependentReport,
    compute_evidence,
    format_log,
    normalised_weights,
)

T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
P = (12.9716, 77.5946)


def reporter(days=0.0, point=P):
    return IndependentReport(point=point, observed_at=T0 + dt.timedelta(days=days))


def test_lone_report_with_perfect_confidence_cannot_reach_full_evidence():
    result = compute_evidence(EvidenceInputs(1.0, [reporter()], 0))
    assert result.score == pytest.approx(0.35)
    assert result.score < 0.70  # below the evidence-confirmed threshold


def test_corroborated_repeated_damage_scores_much_higher_than_a_lone_report():
    lone = compute_evidence(EvidenceInputs(0.6, [reporter()], 0))
    strong = compute_evidence(
        EvidenceInputs(0.6, [reporter(0), reporter(4), reporter(8), reporter(9)], 3)
    )
    assert strong.score > lone.score + 0.4


def test_each_signal_raises_the_score_independently():
    base = compute_evidence(EvidenceInputs(0.5, [reporter()], 0)).score
    assert compute_evidence(EvidenceInputs(0.5, [reporter(), reporter(0)], 0)).score > base
    assert compute_evidence(EvidenceInputs(0.5, [reporter()], 2)).score > base
    assert compute_evidence(EvidenceInputs(0.5, [reporter(0), reporter(5)], 0)).score > base


def test_contributions_sum_to_score_and_weights_to_one():
    result = compute_evidence(EvidenceInputs(0.8, [reporter(0), reporter(3)], 1))
    assert sum(result.contributions.values()) == pytest.approx(result.score)
    assert sum(result.weights.values()) == pytest.approx(1.0)
    assert set(result.components) == set(COMPONENTS)


def test_score_is_always_between_zero_and_one():
    top = compute_evidence(EvidenceInputs(1.0, [reporter(i * 10) for i in range(9)], 99))
    assert 0.0 <= top.score <= 1.0
    assert compute_evidence(EvidenceInputs(0.0, [reporter()], 0)).score == 0.0


def test_weights_come_from_config_and_are_normalised():
    cfg = Settings(
        evidence_weight_ml_confidence=2,
        evidence_weight_observation_count=0,
        evidence_weight_spatial_agreement=0,
        evidence_weight_temporal_consistency=0,
        evidence_weight_community_validation=2,
    )
    assert normalised_weights(cfg)["ml_confidence"] == pytest.approx(0.5)
    result = compute_evidence(EvidenceInputs(1.0, [reporter()], 3), cfg)
    assert result.score == pytest.approx(1.0)


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        normalised_weights(Settings(evidence_weight_ml_confidence=-1))


def test_log_line_lists_every_component_contribution(caplog):
    result = compute_evidence(EvidenceInputs(0.9, [reporter(), reporter(2)], 1))
    line = format_log("detection=abc", result)
    for name in COMPONENTS:
        assert f"{name}=" in line
    assert "score=" in line
