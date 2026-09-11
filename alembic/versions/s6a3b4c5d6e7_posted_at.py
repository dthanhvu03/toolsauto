"""ADR-042: viral_materials.posted_at — Owner bấm "Đã đăng" sau khi đăng tay

Trạng thái POSTED nằm ở cột status sẵn có; cột này giữ mốc giờ để /dadang và báo cáo sau này.

Revision ID: s6a3b4c5d6e7
Revises: r5f2a3b4c5d6
"""
from alembic import op
import sqlalchemy as sa

revision = "s6a3b4c5d6e7"
down_revision = "r5f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("viral_materials", sa.Column("posted_at", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("viral_materials", "posted_at")
