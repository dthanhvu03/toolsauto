"""Add jobs.content_hash + jobs.viral_material_id (PLAN-041 cross-account guard).

Revision ID: f4a1b2c3d4e5
Revises: 883c60c7be10
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "883c60c7be10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BLOCKING = (
    "PENDING",
    "RUNNING",
    "DONE",
    "DRAFT",
    "AI_PROCESSING",
    "AWAITING_STYLE",
)
_STATUS_IN = ", ".join(f"'{s}'" for s in _BLOCKING)


def upgrade() -> None:
    op.add_column("jobs", sa.Column("content_hash", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("viral_material_id", sa.Integer(), nullable=True))
    op.create_index("ix_jobs_content_hash", "jobs", ["content_hash"], unique=False)
    op.create_index("ix_jobs_viral_material_id", "jobs", ["viral_material_id"], unique=False)
    op.create_foreign_key(
        "fk_jobs_viral_material_id",
        "jobs",
        "viral_materials",
        ["viral_material_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Partial uniques (Postgres). App-level gate remains source of clear errors.
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_platform_content_hash_active
        ON jobs (platform, content_hash)
        WHERE content_hash IS NOT NULL
          AND status IN ({_STATUS_IN})
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_viral_material_active
        ON jobs (viral_material_id)
        WHERE viral_material_id IS NOT NULL
          AND status IN ({_STATUS_IN})
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jobs_viral_material_active")
    op.execute("DROP INDEX IF EXISTS idx_jobs_platform_content_hash_active")
    op.drop_constraint("fk_jobs_viral_material_id", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_viral_material_id", table_name="jobs")
    op.drop_index("ix_jobs_content_hash", table_name="jobs")
    op.drop_column("jobs", "viral_material_id")
    op.drop_column("jobs", "content_hash")
