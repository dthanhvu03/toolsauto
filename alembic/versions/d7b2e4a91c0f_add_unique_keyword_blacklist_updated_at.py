"""add unique keyword_blacklist + updated_at

Revision ID: d7b2e4a91c0f
Revises: c4a8f12efb03
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7b2e4a91c0f"
down_revision: Union[str, Sequence[str], None] = "c4a8f12efb03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("keyword_blacklist", schema=None) as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE keyword_blacklist SET updated_at = COALESCE(created_at, CAST(strftime('%s','now') AS INTEGER)) "
            "WHERE updated_at IS NULL"
        )
    )

    op.execute(
        sa.text(
            "DELETE FROM keyword_blacklist WHERE id NOT IN ("
            "SELECT MIN(id) FROM keyword_blacklist GROUP BY LOWER(TRIM(keyword))"
            ")"
        )
    )

    with op.batch_alter_table("keyword_blacklist", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_keyword_blacklist_keyword",
            ["keyword"],
        )


def downgrade() -> None:
    with op.batch_alter_table("keyword_blacklist", schema=None) as batch_op:
        batch_op.drop_constraint("uq_keyword_blacklist_keyword", type_="unique")
        batch_op.drop_column("updated_at")
