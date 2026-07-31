"""accounts.engagement_page_urls + engagement_sessions

PLAN-050: tách nguồn "page FB để dạo" khỏi competitor_urls (vốn là nguồn reup
TikTok), và ghi lại lịch sử phiên nuôi tài khoản để đo được hiệu quả.

Revision ID: h6c3d4e5f6a7
Revises: g5b2c3d4e5f6
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h6c3d4e5f6a7"
down_revision: Union[str, None] = "g5b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("engagement_page_urls", sa.String(), nullable=True),
    )
    op.create_table(
        "engagement_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), index=True),
        sa.Column("action", sa.String(), nullable=True, index=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checkpointed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("target_url", sa.String(), nullable=True),
        sa.Column("urls_touched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("materials_scraped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_sec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.Integer(), nullable=True, index=True),
        sa.Column("finished_at", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("engagement_sessions")
    op.drop_column("accounts", "engagement_page_urls")
