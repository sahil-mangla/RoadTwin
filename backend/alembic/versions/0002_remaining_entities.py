"""Remaining six entities: road_segment, detection, road_observation, road_health, prediction, maintenance_recommendation

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# References the `report_status` enum type revision `0001` already
# created -- `create_type=False` (as in that revision) means this table's
# creation must not attempt a second `CREATE TYPE`.
detection_status_enum = PGEnum(
    "unverified",
    "corroborated",
    "evidence_confirmed",
    "rejected",
    name="report_status",
    create_type=False,
)


def upgrade() -> None:
    # `road_segment` first: it is the parent every other new table but
    # `detection` references.
    op.create_geospatial_table(
        "road_segment",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("segment_identifier", sa.String(), nullable=False, unique=True),
        sa.Column("start_lat", sa.Float(), nullable=False),
        sa.Column("start_lng", sa.Float(), nullable=False),
        sa.Column("end_lat", sa.Float(), nullable=False),
        sa.Column("end_lng", sa.Float(), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry(
                geometry_type="LINESTRING", srid=4326, spatial_index=True
            ),
            nullable=False,
        ),
        sa.Column("road_name", sa.String(), nullable=True),
        sa.Column("road_type", sa.String(), nullable=True),
        sa.Column("length_meters", sa.Float(), nullable=True),
        sa.Column("current_health_score", sa.Float(), nullable=True),
        sa.Column("current_risk_score", sa.Float(), nullable=True),
        sa.Column("deterioration_rate", sa.Float(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # `detection` next: child of `report` (revision 0001).
    op.create_table(
        "detection",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("report.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("damage_type", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox_x1", sa.Float(), nullable=False),
        sa.Column("bbox_y1", sa.Float(), nullable=False),
        sa.Column("bbox_x2", sa.Float(), nullable=False),
        sa.Column("bbox_y2", sa.Float(), nullable=False),
        sa.Column("bbox_area_ratio", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column(
            "status",
            detection_status_enum,
            nullable=False,
            server_default="unverified",
        ),
    )

    op.create_table(
        "road_observation",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "road_segment_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("road_segment.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "report_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("report.id"),
            nullable=False,
        ),
        sa.Column(
            "detection_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("detection.id"),
            nullable=True,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("damage_type", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("verification_score", sa.Float(), nullable=True),
        sa.Column("contribution_weight", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_road_observation_segment_observed_at",
        "road_observation",
        ["road_segment_id", "observed_at"],
    )

    op.create_table(
        "road_health",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "road_segment_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("road_segment.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("health_score", sa.Float(), nullable=False),
        sa.Column("severity_burden", sa.Float(), nullable=True),
        sa.Column("damage_density", sa.Float(), nullable=True),
        sa.Column("evidence_score", sa.Float(), nullable=True),
        sa.Column("deterioration_rate", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_road_health_segment_measured_at",
        "road_health",
        ["road_segment_id", "measured_at"],
    )

    op.create_table(
        "prediction",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "road_segment_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("road_segment.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("predicted_health_score", sa.Float(), nullable=False),
        sa.Column("failure_probability", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("method", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_prediction_segment_generated_at",
        "prediction",
        ["road_segment_id", "generated_at"],
    )

    op.create_table(
        "maintenance_recommendation",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "road_segment_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("road_segment.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("urgency", sa.String(), nullable=False),
        sa.Column("recommended_action", sa.String(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    # Exact reverse of upgrade()'s creation order so no foreign key blocks
    # a drop. Postgres drops a table's own indexes automatically with the
    # table, so no separate index-drop calls are needed.
    op.drop_table("maintenance_recommendation")
    op.drop_table("prediction")
    op.drop_table("road_health")
    op.drop_table("road_observation")
    op.drop_table("detection")
    op.drop_geospatial_table("road_segment")
    # Deliberately NOT touching `report`, the `report_status` enum type, or
    # the PostGIS extension -- revision 0001 owns all three.
