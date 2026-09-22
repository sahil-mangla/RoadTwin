"""Pure unit tests for the Report contract -- no database fixture required."""

import pytest
from pydantic import ValidationError

from backend.models.enums import ReportStatus
from backend.models.geo import make_point
from backend.models.report import Report
from backend.schemas.report import ReportCreate


def _valid_payload(**overrides):
    payload = {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "gps_accuracy_meters": 8.5,
    }
    payload.update(overrides)
    return payload


def test_latitude_above_range_raises():
    with pytest.raises(ValidationError):
        ReportCreate(**_valid_payload(latitude=91))


def test_latitude_below_range_raises():
    with pytest.raises(ValidationError):
        ReportCreate(**_valid_payload(latitude=-91))


def test_longitude_above_range_raises():
    with pytest.raises(ValidationError):
        ReportCreate(**_valid_payload(longitude=181))


def test_longitude_below_range_raises():
    with pytest.raises(ValidationError):
        ReportCreate(**_valid_payload(longitude=-181))


def test_negative_accuracy_raises():
    with pytest.raises(ValidationError):
        ReportCreate(**_valid_payload(gps_accuracy_meters=-1))


def test_valid_payload_validates():
    report = ReportCreate(**_valid_payload())
    assert report.latitude == 12.9716
    assert report.longitude == 77.5946
    assert report.gps_accuracy_meters == 8.5


def test_report_instance_defaults_to_unverified_before_flush():
    report = Report(
        latitude=12.9716,
        longitude=77.5946,
        gps_accuracy_meters=8.5,
        timestamp=None,
        location=make_point(12.9716, 77.5946),
    )
    assert report.status == ReportStatus.UNVERIFIED


def test_make_point_orders_longitude_first():
    point = make_point(12.9716, 77.5946)
    assert point.srid == 4326
    assert point.data.index("77.5946") < point.data.index("12.9716")
