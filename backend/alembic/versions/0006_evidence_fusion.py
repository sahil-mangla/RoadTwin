"""Evidence fusion: report_corroboration table, road_observation audit columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_corroboration",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("report_id", sa.Uuid(as_uuid=True), sa.ForeignKey("report.id"), nullable=False),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.UniqueConstraint(
            "report_id", "identity_key", name="uq_report_corroboration_report_identity"
        ),
    )
    op.create_index("ix_report_corroboration_report_id", "report_corroboration", ["report_id"])
    op.create_index(
        "ix_report_corroboration_ip_created", "report_corroboration", ["ip_address", "created_at"]
    )

    op.add_column(
        "road_observation", sa.Column("evidence_components", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "road_observation",
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("road_observation", "recorded_at")
    op.drop_column("road_observation", "evidence_components")
    op.drop_index("ix_report_corroboration_ip_created", table_name="report_corroboration")
    op.drop_index("ix_report_corroboration_report_id", table_name="report_corroboration")
    op.drop_table("report_corroboration")
