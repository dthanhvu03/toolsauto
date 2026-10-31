"""PLAN-112 — studio_channels.dub_voice: giọng VieNeu riêng của kênh (NULL = theo mẫu).

Revision ID: x1f8a9b0c1d2
Revises: w0e7f8a9b0c1
Create Date: 2026-10-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "x1f8a9b0c1d2"
down_revision = "w0e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("studio_channels", sa.Column("dub_voice", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("studio_channels", "dub_voice")
