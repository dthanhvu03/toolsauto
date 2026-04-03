"""add_fb_compliance_tables

Revision ID: c4a8f12efb03
Revises: ad3ebb5bf76c
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4a8f12efb03"
down_revision: Union[str, Sequence[str], None] = "ad3ebb5bf76c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "keyword_blacklist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_keyword_blacklist_keyword",
        "keyword_blacklist",
        ["keyword"],
        unique=False,
    )
    op.create_index(
        "ix_keyword_blacklist_category",
        "keyword_blacklist",
        ["category"],
        unique=False,
    )

    op.create_table(
        "violation_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("affiliate_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("original_content", sa.Text(), nullable=True),
        sa.Column("rewritten_content", sa.Text(), nullable=True),
        sa.Column("violations_found", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.String(), nullable=True),
        sa.Column("checked_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_violation_log_affiliate_id",
        "violation_log",
        ["affiliate_id"],
        unique=False,
    )
    op.create_index(
        "ix_violation_log_action",
        "violation_log",
        ["action_taken"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_violation_log_action", table_name="violation_log")
    op.drop_index("ix_violation_log_affiliate_id", table_name="violation_log")
    op.drop_table("violation_log")
    op.drop_index("ix_keyword_blacklist_category", table_name="keyword_blacklist")
    op.drop_index("ix_keyword_blacklist_keyword", table_name="keyword_blacklist")
    op.drop_table("keyword_blacklist")
