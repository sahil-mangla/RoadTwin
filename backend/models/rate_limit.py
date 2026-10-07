"""The `SubmissionAttempt` entity -- rate-limit telemetry (INGT-03, D-03/D-04).

Deliberately NOT protected by `AppendOnlyRepository`: this table is
operational rate-limit telemetry, prunable by design (see
`Settings.submission_attempt_retention_days` and
`backend/services/ingestion/rate_limit.py`'s `prune_old_attempts`), not the
longitudinal intelligence-layer evidence SCHM-02 protects (RoadObservation,
RoadHealth, Prediction). A row here records one accepted submission
attempt for the purpose of counting recent activity, and is never updated
after insert -- append-and-count, not append-and-mutate -- but its
deletability distinguishes it from the append-only evidence tables.
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampedMixin, UUIDPKMixin


class SubmissionAttempt(UUIDPKMixin, TimestampedMixin, Base):
    __tablename__ = "submission_attempt"
    # Composite indexes back the rolling-window COUNT queries
    # (identity_key, created_at) and (ip_address, created_at) that
    # backend/services/ingestion/rate_limit.py runs on every submission.
    __table_args__ = (
        sa.Index("ix_submission_attempt_identity_created", "identity_key", "created_at"),
        sa.Index("ix_submission_attempt_ip_created", "ip_address", "created_at"),
    )

    identity_key: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    # 45 characters is IPv6-safe.
    ip_address: Mapped[str] = mapped_column(sa.String(45), nullable=False, index=True)
