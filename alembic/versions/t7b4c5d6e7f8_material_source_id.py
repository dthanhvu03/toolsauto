"""Gắn video mới về nguồn đã quét ra nó.

Cột trống được. Video cũ và video dán tay để trống, không điền lại và không xóa.

Revision ID: t7b4c5d6e7f8
Revises: s6a3b4c5d6e7
"""
from alembic import op
import sqlalchemy as sa

revision = "t7b4c5d6e7f8"
down_revision = "s6a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("viral_materials", sa.Column("source_id", sa.Integer(), nullable=True))
    op.create_index("ix_viral_materials_source_id", "viral_materials", ["source_id"])
    op.create_foreign_key(
        "fk_viral_materials_source_id", "viral_materials", "viral_sources",
        ["source_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_viral_materials_source_id", "viral_materials", type_="foreignkey")
    op.drop_index("ix_viral_materials_source_id", table_name="viral_materials")
    op.drop_column("viral_materials", "source_id")
