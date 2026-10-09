"""Overlapping same-class boxes collapse to one defect."""

from backend.services.perception.detector import RawDetection
from backend.services.perception.postprocess import merge_overlapping


def test_nested_boxes_of_same_class_keep_most_confident():
    big = RawDetection("D20", 0.76, 0, 4, 612, 373)
    top = RawDetection("D20", 0.70, 0, 6, 612, 203)
    bottom = RawDetection("D20", 0.50, 11, 209, 611, 399)
    assert merge_overlapping([top, bottom, big]) == [big]


def test_different_classes_are_not_merged():
    crack = RawDetection("D00", 0.9, 0, 0, 100, 100)
    pothole = RawDetection("D40", 0.8, 10, 10, 90, 90)
    assert len(merge_overlapping([crack, pothole])) == 2


def test_separate_boxes_of_same_class_are_kept():
    a = RawDetection("D40", 0.9, 0, 0, 50, 50)
    b = RawDetection("D40", 0.8, 200, 200, 260, 260)
    assert len(merge_overlapping([a, b])) == 2


def test_empty_input():
    assert merge_overlapping([]) == []
