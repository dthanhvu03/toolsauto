"""P037 Phase 3: update platform_configs.adapter_class for tiktok

Revision ID: c7d9e1f2a3b4
Revises: b4c8f0e9d3a1
"""
from alembic import op

revision = "c7d9e1f2a3b4"
down_revision = "b4c8f0e9d3a1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE platform_configs
        SET adapter_class = 'app.features.tiktok.adapter.TiktokAdapter'
        WHERE platform = 'tiktok'
          AND adapter_class = 'app.adapters.tiktok.adapter.TiktokAdapter'
    """)


def downgrade():
    op.execute("""
        UPDATE platform_configs
        SET adapter_class = 'app.adapters.tiktok.adapter.TiktokAdapter'
        WHERE platform = 'tiktok'
          AND adapter_class = 'app.features.tiktok.adapter.TiktokAdapter'
    """)
