"""ADR-041: viral_materials — chia video dài thành nhiều phần

Phần con là một material có cha (`parent_material_id`), biết mình là phần mấy
(`part_index`/`part_total`). Kế hoạch chia đã đề nghị (`split_plan`, JSON) lưu trên cha.

Revision ID: r5f2a3b4c5d6
Revises: q4e1f2a3b4c5
"""
from alembic import op
import sqlalchemy as sa

revision = "r5f2a3b4c5d6"
down_revision = "q4e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("viral_materials", sa.Column("parent_material_id", sa.Integer(), nullable=True))
    op.add_column("viral_materials", sa.Column("part_index", sa.Integer(), nullable=True))
    op.add_column("viral_materials", sa.Column("part_total", sa.Integer(), nullable=True))
    op.add_column("viral_materials", sa.Column("split_plan", sa.Text(), nullable=True))
    op.create_index("ix_viral_materials_parent_material_id", "viral_materials", ["parent_material_id"])
    op.create_foreign_key(
        "fk_viral_materials_parent", "viral_materials", "viral_materials",
        ["parent_material_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_viral_materials_parent", "viral_materials", type_="foreignkey")
    op.drop_index("ix_viral_materials_parent_material_id", table_name="viral_materials")
    op.drop_column("viral_materials", "split_plan")
    op.drop_column("viral_materials", "part_total")
    op.drop_column("viral_materials", "part_index")
    op.drop_column("viral_materials", "parent_material_id")
