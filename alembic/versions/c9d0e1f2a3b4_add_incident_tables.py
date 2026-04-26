"""add incident logging tables

Revision ID: c9d0e1f2a3b4
Revises: f2a3b4c5d6e8
Create Date: 2026-04-26 15:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("incident_logs"):
        op.create_table(
            "incident_logs",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("platform", sa.String(), nullable=False),
            sa.Column("feature", sa.String(), nullable=True),
            sa.Column("category", sa.String(), server_default="unknown", nullable=False),
            sa.Column("worker_name", sa.String(), nullable=True),
            sa.Column("job_id", sa.String(), nullable=True),
            sa.Column("account_id", sa.String(), nullable=True),
            sa.Column("severity", sa.String(), nullable=False),
            sa.Column("error_type", sa.String(), nullable=False),
            sa.Column("error_signature", sa.String(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("stacktrace", sa.Text(), nullable=True),
            sa.Column(
                "context_json",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
            sa.Column("source_log_ref", sa.Text(), nullable=True),
            sa.Column("resolved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.CheckConstraint(
                "category IN ('ui_drift','auth','proxy','db','network','rate_limit','worker_crash','resource','unknown')",
                name="ck_incident_logs_category",
            ),
            sa.CheckConstraint(
                "severity IN ('warning','error','critical')",
                name="ck_incident_logs_severity",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_incident_signature_time", "incident_logs", ["error_signature", "occurred_at"], unique=False)
        op.create_index("idx_incident_platform_time", "incident_logs", ["platform", "occurred_at"], unique=False)
        op.create_index("idx_incident_account_time", "incident_logs", ["account_id", "occurred_at"], unique=False)
        op.create_index("idx_incident_severity_time", "incident_logs", ["severity", "occurred_at"], unique=False)
        op.create_index("idx_incident_category_time", "incident_logs", ["category", "occurred_at"], unique=False)
        op.create_index("idx_incident_occurred_at", "incident_logs", ["occurred_at"], unique=False)
        op.create_index("idx_incident_job_id", "incident_logs", ["job_id"], unique=False)

    if not inspector.has_table("incident_groups"):
        op.create_table(
            "incident_groups",
            sa.Column("error_signature", sa.String(), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("occurrence_count", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
            sa.Column("last_job_id", sa.String(), nullable=True),
            sa.Column("last_account_id", sa.String(), nullable=True),
            sa.Column("last_platform", sa.String(), nullable=True),
            sa.Column("last_worker_name", sa.String(), nullable=True),
            sa.Column("last_sample_message", sa.Text(), nullable=True),
            sa.Column("severity_max", sa.String(), nullable=False),
            sa.Column("status", sa.String(), server_default="open", nullable=False),
            sa.Column("acknowledged_by", sa.String(), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "status IN ('open','acknowledged','resolved','ignored')",
                name="ck_incident_groups_status",
            ),
            sa.PrimaryKeyConstraint("error_signature"),
        )
        op.create_index("idx_groups_status_lastseen", "incident_groups", ["status", "last_seen_at"], unique=False)
        op.create_index("idx_groups_count", "incident_groups", ["occurrence_count"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("incident_groups"):
        op.drop_index("idx_groups_count", table_name="incident_groups")
        op.drop_index("idx_groups_status_lastseen", table_name="incident_groups")
        op.drop_table("incident_groups")

    if inspector.has_table("incident_logs"):
        op.drop_index("idx_incident_job_id", table_name="incident_logs")
        op.drop_index("idx_incident_occurred_at", table_name="incident_logs")
        op.drop_index("idx_incident_category_time", table_name="incident_logs")
        op.drop_index("idx_incident_severity_time", table_name="incident_logs")
        op.drop_index("idx_incident_account_time", table_name="incident_logs")
        op.drop_index("idx_incident_platform_time", table_name="incident_logs")
        op.drop_index("idx_incident_signature_time", table_name="incident_logs")
        op.drop_table("incident_logs")
