"""PERC-02: severity comes from bbox area and damage type, not confidence."""

import pytest

from backend.services.perception.severity import bbox_area_ratio, canonical_damage_type, derive_severity


def test_area_ratio_is_fraction_of_image():
    assert bbox_area_ratio(0, 0, 50, 50, 100, 100) == pytest.approx(0.25)


def test_area_ratio_clamps_box_outside_image():
    assert bbox_area_ratio(-10, -10, 200, 200, 100, 100) == 1.0


def test_area_ratio_rejects_bad_dimensions():
    with pytest.raises(ValueError):
        bbox_area_ratio(0, 0, 1, 1, 0, 100)


@pytest.mark.parametrize(
    "damage_type,ratio,expected",
    [
        ("D40", 0.01, "low"),
        ("D40", 0.05, "moderate"),
        ("D40", 0.15, "high"),
        ("D40", 0.5, "critical"),
        ("D00", 0.01, "moderate"),  # thin crack boxes are weighted up
        ("D99", 0.01, "moderate"),  # unknown class uses the default multiplier
    ],
)
def test_derive_severity(damage_type, ratio, expected):
    assert derive_severity(damage_type, ratio) == expected


def test_severity_signature_has_no_confidence_input():
    # Guards PERC-02: confidence must not be an input.
    import inspect

    assert list(inspect.signature(derive_severity).parameters) == ["damage_type", "area_ratio"]


@pytest.mark.parametrize(
    "name,code",
    [("Longitudinal Crack", "D00"), ("Transverse Crack", "D10"), ("Alligator Crack", "D20"),
     ("Potholes", "D40"), ("D20", "D20"), ("mystery", "mystery")],
)
def test_canonical_damage_type(name, code):
    assert canonical_damage_type(name) == code
