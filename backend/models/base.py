"""Shared SQLAlchemy 2.0 declarative base and mixins.

Only the SQLAlchemy 2.0 typed `Mapped[...]` / `mapped_column()` declarative
style is used anywhere in this codebase -- the legacy SQLAlchemy 1.x
imperative attribute-assignment style is prohibited in new code
(01-RESEARCH.md State of the Art).
"""

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPKMixin:
    """UUID v4 primary key, generated client-side (D-05).

    Client-side generation (`default=uuid.uuid4`, not
    `server_default=func.gen_random_uuid()`) is deliberate: Phase 3's arq
    background worker needs a newly-created row's identifier immediately
    after construction, before any database round-trip
    (01-RESEARCH.md Pattern 2 / Anti-Pattern note).
    """

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampedMixin:
    """Server-side insert timestamp, distinct from any client-reported time."""

    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
