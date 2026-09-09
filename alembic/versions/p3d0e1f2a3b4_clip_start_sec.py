"""ADR-031: viral_materials.clip_start_sec — mốc bắt đầu cắt trong video gốc

Video nguồn dài 6-11 phút, tool chỉ giữ 90 giây đầu (cảnh móc mồi) và cắt bỏ đúng đoạn
câu được cá. Cột này cho Owner chỉ mốc bắt đầu; None/0 giữ nguyên hành vi cũ.

Revision ID: p3d0e1f2a3b4
Revises: n2c9d0e1f2a3
"""
from alembic import op
import sqlalchemy as sa

revision = "p3d0e1f2a3b4"
down_revision = "n2c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("viral_materials", sa.Column("clip_start_sec", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("viral_materials", "clip_start_sec")
