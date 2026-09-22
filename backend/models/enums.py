"""Shared status lifecycle enum for Report and Detection (SCHM-03, D-06).

`rejected` is reserved now, ahead of need, for the v2 moderation-flag path
(REQUIREMENTS.md MODR-01) so that no `ALTER TYPE ... ADD VALUE` migration
is required later -- Postgres enum-value additions are a documented
migration quirk (01-RESEARCH.md Pitfall 4), and reserving the value up
front sidesteps it entirely for the values already known to be needed.
"""

import enum

import sqlalchemy as sa

from .base import Base


class ReportStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    EVIDENCE_CONFIRMED = "evidence_confirmed"
    REJECTED = "rejected"


# One shared Postgres enum type, referenced by both `report.status` and
# `detection.status` (Plan 04) -- so Postgres gets exactly one enum type
# and Alembic emits exactly one `CREATE TYPE`, per 01-RESEARCH.md Pattern 3.
report_status_enum = sa.Enum(ReportStatus, name="report_status", metadata=Base.metadata)
