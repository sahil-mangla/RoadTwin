"""Health & forecast: road_health.components, prediction.explanation, forecast_evaluation

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("road_health", sa.Column("components", postgresql.JSONB(), nullable=True))
    op.add_column("prediction", sa.Column("explanation", sa.Text(), nullable=True))

    op.create_table(
        "forecast_evaluation",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("prediction_id", sa.Uuid(as_uuid=True), sa.ForeignKey("prediction.id"), nullable=False),
        sa.Column("road_segment_id", sa.Uuid(as_uuid=True), sa.ForeignKey("road_segment.id"), nullable=False),
        sa.Column("road_health_id", sa.Uuid(as_uuid=True), sa.ForeignKey("road_health.id"), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("target_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_health_score", sa.Float(), nullable=False),
        sa.Column("actual_health_score", sa.Float(), nullable=False),
        sa.Column("error", sa.Float(), nullable=False),
        sa.Column("absolute_error", sa.Float(), nullable=False),
        sa.UniqueConstraint("prediction_id", name="uq_forecast_evaluation_prediction"),
    )
    op.create_index(
        "ix_forecast_evaluation_road_segment_id", "forecast_evaluation", ["road_segment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_evaluation_road_segment_id", table_name="forecast_evaluation")
    op.drop_table("forecast_evaluation")
    op.drop_column("prediction", "explanation")
    op.drop_column("road_health", "components")
