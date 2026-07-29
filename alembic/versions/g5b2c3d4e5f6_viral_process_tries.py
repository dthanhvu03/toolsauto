"""add viral_materials.process_tries

Revision ID: g5b2c3d4e5f6
Revises: f4a1b2c3d4e5
Create Date: 2026-07-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g5b2c3d4e5f6"
down_revision: Union[str, None] = "f4a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "viral_materials",
        sa.Column("process_tries", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("viral_materials", "process_tries")
