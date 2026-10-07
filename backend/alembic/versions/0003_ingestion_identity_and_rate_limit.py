"""Ingestion identity + rate limiting: report.submitter_identity_key, submission_attempt table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "report", sa.Column("submitter_identity_key", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_report_submitter_identity_key", "report", ["submitter_identity_key"]
    )
    op.alter_column(
        "report",
        "image_path",
        type_=sa.String(256),
        existing_type=sa.String(),
        existing_nullable=True,
    )

    op.create_table(
        "submission_attempt",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
    )
    op.create_index(
        "ix_submission_attempt_identity_key", "submission_attempt", ["identity_key"]
    )
    op.create_index(
        "ix_submission_attempt_ip_address", "submission_attempt", ["ip_address"]
    )
    op.create_index(
        "ix_submission_attempt_identity_created",
        "submission_attempt",
        ["identity_key", "created_at"],
    )
    op.create_index(
        "ix_submission_attempt_ip_created",
        "submission_attempt",
        ["ip_address", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_submission_attempt_ip_created", table_name="submission_attempt")
    op.drop_index(
        "ix_submission_attempt_identity_created", table_name="submission_attempt"
    )
    op.drop_index("ix_submission_attempt_ip_address", table_name="submission_attempt")
    op.drop_index("ix_submission_attempt_identity_key", table_name="submission_attempt")
    op.drop_table("submission_attempt")

    op.alter_column(
        "report",
        "image_path",
        type_=sa.String(),
        existing_type=sa.String(256),
        existing_nullable=True,
    )
    op.drop_index("ix_report_submitter_identity_key", table_name="report")
    op.drop_column("report", "submitter_identity_key")
