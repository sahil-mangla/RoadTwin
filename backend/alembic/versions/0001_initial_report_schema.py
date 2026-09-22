"""Initial migration: PostGIS extension, report_status enum type, report table

Revision ID: 0001
Revises:
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: the plain `sa.Enum(..., create_type=False)` does not reliably
# suppress the implicit `CREATE TYPE` DDL event on table creation in this
# SQLAlchemy version -- the `create_type` flag is only honoured by the
# PostgreSQL-dialect-specific `ENUM` type. Using `postgresql.ENUM` here
# (rather than the generic `sa.Enum`) is what actually makes
# `create_type=False` on the column below suppress the second `CREATE
# TYPE` attempt after this module-level enum object creates the type
# explicitly in `upgrade()`.
report_status_enum = PGEnum(
    "unverified",
    "corroborated",
    "evidence_confirmed",
    "rejected",
    name="report_status",
)


def upgrade() -> None:
    # Must precede every other statement -- the `geometry` type does not
    # exist until the extension is installed.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    report_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_geospatial_table(
        "report",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("image_path", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("gps_accuracy_meters", sa.Float(), nullable=True),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("community_upvotes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verification_score", sa.Float(), nullable=True),
        sa.Column(
            "status",
            PGEnum(
                "unverified",
                "corroborated",
                "evidence_confirmed",
                "rejected",
                name="report_status",
                create_type=False,
            ),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_geospatial_table("report")
    report_status_enum.drop(op.get_bind(), checkfirst=True)
    # Deliberately NOT dropping the `postgis` extension: `CREATE EXTENSION
    # IF NOT EXISTS` makes re-upgrade idempotent, and dropping the
    # extension here would cascade into anything else in the database that
    # depends on it.
