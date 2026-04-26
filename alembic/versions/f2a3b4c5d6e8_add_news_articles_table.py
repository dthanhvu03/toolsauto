"""add news_articles table

Revision ID: f2a3b4c5d6e8
Revises: e806f6ae8107
Create Date: 2026-04-25 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e8'
down_revision: Union[str, Sequence[str], None] = 'e806f6ae8107'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table('news_articles'):
        op.create_table('news_articles',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_url', sa.String(), nullable=False),
            sa.Column('source_name', sa.String(), nullable=True),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('content', sa.Text(), nullable=True),
            sa.Column('image_url', sa.String(), nullable=True),
            sa.Column('category', sa.String(), nullable=True),
            sa.Column('published_at', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(), nullable=True),
            sa.Column('created_at', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_news_articles_id'), 'news_articles', ['id'], unique=False)
        op.create_index(op.f('ix_news_articles_source_url'), 'news_articles', ['source_url'], unique=True)
        op.create_index(op.f('ix_news_articles_category'), 'news_articles', ['category'], unique=False)
        op.create_index(op.f('ix_news_articles_published_at'), 'news_articles', ['published_at'], unique=False)
        op.create_index(op.f('ix_news_articles_status'), 'news_articles', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_news_articles_status'), table_name='news_articles')
    op.drop_index(op.f('ix_news_articles_published_at'), table_name='news_articles')
    op.drop_index(op.f('ix_news_articles_category'), table_name='news_articles')
    op.drop_index(op.f('ix_news_articles_source_url'), table_name='news_articles')
    op.drop_index(op.f('ix_news_articles_id'), table_name='news_articles')
    op.drop_table('news_articles')
