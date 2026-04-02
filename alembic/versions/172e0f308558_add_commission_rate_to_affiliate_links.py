"""add_commission_rate_to_affiliate_links

Revision ID: 172e0f308558
Revises: b11500c5c2f2
Create Date: 2026-04-02 10:39:19.248990

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '172e0f308558'
down_revision: Union[str, Sequence[str], None] = 'b11500c5c2f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('affiliate_links', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('commission_rate', sa.Float(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('affiliate_links', schema=None) as batch_op:
        batch_op.drop_column('commission_rate')
