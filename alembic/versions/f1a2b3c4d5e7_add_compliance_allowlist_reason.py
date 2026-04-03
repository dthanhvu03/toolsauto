"""add compliance_allowlist.reason column

Revision ID: f1a2b3c4d5e7
Revises: e3f1a2b4c5d6
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e7"
down_revision: Union[str, Sequence[str], None] = "e3f1a2b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("compliance_allowlist", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reason", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("compliance_allowlist", schema=None) as batch_op:
        batch_op.drop_column("reason")
