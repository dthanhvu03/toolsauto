"""bang viral_sources — nguon quet tu dong doc lap account (ADR-019)

Quet kenh TikTok truoc gio doc `Account.competitor_urls` cua account ACTIVE:
0 account active => quet chet theo. Bang nay giu nguon (TikTok @handle, YouTube
@handle/shorts) rieng, worker maintenance quet moi vong; material tao ra co
`scraped_by_account_id = NULL` va duoc sweep gom rieng (ADR-018: khong account -> READY).

`min_views` / `max_videos` NULL = dung setting `viral.min_views` /
`viral.max_videos_per_channel`. `last_scanned_at` la epoch giay.

Revision ID: k9f6a7b8c9d0
Revises: j8e5f6a7b8c9
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k9f6a7b8c9d0"
down_revision: Union[str, None] = "j8e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "viral_sources"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("handle", sa.String(), nullable=True),
        sa.Column("min_views", sa.Integer(), nullable=True),
        sa.Column("max_videos", sa.Integer(), nullable=True),
        sa.Column("target_page", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_scanned_at", sa.Integer(), nullable=True),
        sa.Column("last_found", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.Integer(), nullable=True),
    )
    op.create_index("ix_viral_sources_id", TABLE, ["id"])
    op.create_index("ix_viral_sources_url", TABLE, ["url"], unique=True)
    op.create_index("ix_viral_sources_enabled", TABLE, ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_viral_sources_enabled", table_name=TABLE)
    op.drop_index("ix_viral_sources_url", table_name=TABLE)
    op.drop_index("ix_viral_sources_id", table_name=TABLE)
    op.drop_table(TABLE)
