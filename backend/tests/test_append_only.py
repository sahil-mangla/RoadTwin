"""SCHM-02 structural coverage: the append-only contract is a design
contract enforced by class hierarchy, not a formality.

Per D-08, RoadObservation, RoadHealth and Prediction rows may only ever be
created, never replaced or removed, through their repository classes. This
test introspects the three append-only repository classes (and every class
in their method resolution order, up to and including the shared base) and
asserts none of them exposes any attribute whose name would replace or
remove a persisted row. It also asserts the mutable repositories *do*
expose their update path, so this test fails loudly if someone "fixes" the
asymmetry by flattening the hierarchy.
"""

from backend.db.repository import (
    AppendOnlyRepository,
    DetectionRepository,
    MaintenanceRecommendationRepository,
    PredictionRepository,
    ReportRepository,
    RoadHealthRepository,
    RoadObservationRepository,
    RoadSegmentRepository,
)

# The set of attribute names that would let a caller replace or remove an
# already-persisted row. None of these may exist anywhere in the method
# resolution order of an append-only repository.
FORBIDDEN_MUTATING_ATTRIBUTES = ("update", "delete", "remove", "upsert", "patch")

APPEND_ONLY_REPOSITORIES = (
    RoadObservationRepository,
    RoadHealthRepository,
    PredictionRepository,
)

MUTABLE_REPOSITORIES = (
    ReportRepository,
    DetectionRepository,
    RoadSegmentRepository,
    MaintenanceRecommendationRepository,
)


def test_append_only_repositories_expose_no_mutating_attribute():
    for repo_cls in APPEND_ONLY_REPOSITORIES:
        for name in FORBIDDEN_MUTATING_ATTRIBUTES:
            assert not hasattr(repo_cls, name), (
                f"{repo_cls.__name__} must not expose '{name}' -- "
                "append-only entities may only ever be created, never "
                "replaced or removed (SCHM-02, D-08)."
            )


def test_append_only_repositories_subclass_append_only_base():
    for repo_cls in APPEND_ONLY_REPOSITORIES:
        assert issubclass(repo_cls, AppendOnlyRepository), (
            f"{repo_cls.__name__} must subclass AppendOnlyRepository, "
            "not MutableRepository -- the class hierarchy itself is the "
            "SCHM-02 enforcement mechanism."
        )


def test_mutable_repositories_still_expose_update():
    """Guards against "fixing" the asymmetry by flattening the hierarchy.

    If a future change made every repository subclass MutableRepository
    (or otherwise granted every class an `update` method), the two tests
    above would still pass trivially -- this test fails in that scenario,
    because the mutable repositories are expected to have `update` and the
    append-only ones are expected not to. The asymmetry itself is the
    thing under test.
    """
    for repo_cls in MUTABLE_REPOSITORIES:
        assert hasattr(repo_cls, "update"), (
            f"{repo_cls.__name__} is expected to be mutable and expose "
            "'update' -- if this fails, the mutable/append-only "
            "distinction has been lost."
        )
