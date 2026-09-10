"""ADR-036: viral_materials.clip_length_sec — độ dài riêng cho từng video

Mốc bắt đầu (ADR-031) mới là một đầu; muốn một đoạn TRỌN VẸN phải chọn được cả hai.

Revision ID: q4e1f2a3b4c5
Revises: p3d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "q4e1f2a3b4c5"
down_revision = "p3d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("viral_materials", sa.Column("clip_length_sec", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("viral_materials", "clip_length_sec")
