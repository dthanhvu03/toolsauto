"""P037 Phase 3: update platform_configs.adapter_class for instagram

Revision ID: b4c8f0e9d3a1
Revises: a8e7f6d5c4b3
Create Date: 2026-05-04
"""

from alembic import op


revision = "b4c8f0e9d3a1"
down_revision = "a8e7f6d5c4b3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE platform_configs
        SET adapter_class = 'app.features.instagram.adapter.InstagramAdapter'
        WHERE platform = 'instagram'
          AND adapter_class = 'app.adapters.instagram.adapter.InstagramAdapter'
    """)


def downgrade():
    op.execute("""
        UPDATE platform_configs
        SET adapter_class = 'app.adapters.instagram.adapter.InstagramAdapter'
        WHERE platform = 'instagram'
          AND adapter_class = 'app.features.instagram.adapter.InstagramAdapter'
    """)
