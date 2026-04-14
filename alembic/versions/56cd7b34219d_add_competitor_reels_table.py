"""add_competitor_reels_table

Revision ID: 56cd7b34219d
Revises: 4215e86b6614
Create Date: 2026-04-14 04:26:58.609943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56cd7b34219d'
down_revision: Union[str, Sequence[str], None] = '4215e86b6614'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Surgical upgrade: only create competitor_reels table."""
    # Using batch_op for SQLite compatibility where safe, but create_table is top-level
    op.create_table('competitor_reels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reel_url', sa.String(), nullable=False),
        sa.Column('scrape_date', sa.String(), nullable=False),
        sa.Column('page_url', sa.String(), nullable=True),
        sa.Column('views', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('likes', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('comments', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('shares', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('caption', sa.String(), nullable=True),
        sa.Column('recorded_at', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    with op.batch_alter_table('competitor_reels', schema=None) as batch_op:
        batch_op.create_index('ix_competitor_reels_id', ['id'], unique=False)
        batch_op.create_index('ix_competitor_reels_reel_url', ['reel_url'], unique=False)
        batch_op.create_index('ix_competitor_reels_scrape_date', ['scrape_date'], unique=False)
        batch_op.create_index('ix_competitor_reels_recorded_at', ['recorded_at'], unique=False)
        batch_op.create_index('idx_competitor_dedup', ['reel_url', 'scrape_date'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('competitor_reels')
