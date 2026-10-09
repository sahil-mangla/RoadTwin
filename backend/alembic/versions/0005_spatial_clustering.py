"""Spatial clustering: report.duplicate_of_id, report.segment_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "report",
        sa.Column("duplicate_of_id", sa.Uuid(as_uuid=True), sa.ForeignKey("report.id"), nullable=True),
    )
    op.add_column(
        "report",
        sa.Column("segment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("road_segment.id"), nullable=True),
    )
    op.create_index("ix_report_duplicate_of_id", "report", ["duplicate_of_id"])
    op.create_index("ix_report_segment_id", "report", ["segment_id"])


def downgrade() -> None:
    op.drop_index("ix_report_segment_id", table_name="report")
    op.drop_index("ix_report_duplicate_of_id", table_name="report")
    op.drop_column("report", "segment_id")
    op.drop_column("report", "duplicate_of_id")
