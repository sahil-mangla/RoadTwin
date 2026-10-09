"""Authority & priority: staff_user, repair_event, citizen_notification, segment repair/enhancement columns

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps():
    return [
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.add_column(
        "road_segment",
        sa.Column("repair_status", sa.String(16), server_default="none", nullable=False),
    )
    op.add_column("road_segment", sa.Column("last_repaired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("road_segment", sa.Column("traffic_exposure", sa.Float(), nullable=True))
    op.add_column("road_segment", sa.Column("near_vulnerable_location", sa.Boolean(), nullable=True))
    op.add_column(
        "maintenance_recommendation",
        sa.Column("components", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "staff_user",
        *_timestamps(),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "repair_event",
        *_timestamps(),
        sa.Column("road_segment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("road_segment.id"), nullable=False),
        sa.Column("staff_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("staff_user.id"), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=False),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_repair_event_road_segment_id", "repair_event", ["road_segment_id"])
    op.create_table(
        "citizen_notification",
        *_timestamps(),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("report_id", sa.Uuid(as_uuid=True), sa.ForeignKey("report.id"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_citizen_notification_identity_key", "citizen_notification", ["identity_key"])


def downgrade() -> None:
    op.drop_index("ix_citizen_notification_identity_key", table_name="citizen_notification")
    op.drop_table("citizen_notification")
    op.drop_index("ix_repair_event_road_segment_id", table_name="repair_event")
    op.drop_table("repair_event")
    op.drop_table("staff_user")
    op.drop_column("maintenance_recommendation", "components")
    op.drop_column("road_segment", "near_vulnerable_location")
    op.drop_column("road_segment", "traffic_exposure")
    op.drop_column("road_segment", "last_repaired_at")
    op.drop_column("road_segment", "repair_status")
