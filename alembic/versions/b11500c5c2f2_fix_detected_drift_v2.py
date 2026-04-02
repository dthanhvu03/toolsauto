"""fix_detected_drift_v2

Revision ID: b11500c5c2f2
Revises: a61a4e534d5b
Create Date: 2026-04-02 09:18:02.759651

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b11500c5c2f2'
down_revision: Union[str, Sequence[str], None] = 'a61a4e534d5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Minimalist version for SQLite compatibility."""
    # Accounts
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        # batch_op.drop_index('idx_accounts_profile')
        batch_op.create_index(batch_op.f('ix_accounts_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_accounts_login_status'), ['login_status'], unique=False)
        batch_op.create_unique_constraint('uq_accounts_profile_path', ['profile_path'])

    # Discovered Channels
    with op.batch_alter_table('discovered_channels', schema=None) as batch_op:
        # batch_op.drop_index('ix_discovered_channels_account_id')
        # batch_op.drop_index('ix_discovered_channels_url_acc')
        batch_op.create_index(batch_op.f('ix_discovered_channels_id'), ['id'], unique=False)

    # Jobs
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        # batch_op.drop_index('idx_jobs_last_metrics_check')
        # batch_op.drop_index('idx_jobs_scheduled')
        # batch_op.drop_index('idx_jobs_tracking')
        batch_op.create_index(batch_op.f('ix_jobs_batch_id'), ['batch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_dedupe_key'), ['dedupe_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_finished_at'), ['finished_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_last_heartbeat_at'), ['last_heartbeat_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_last_metrics_check_ts'), ['last_metrics_check_ts'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_scheduled_at'), ['scheduled_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_tracking_code'), ['tracking_code'], unique=False)

    # Page Insights
    with op.batch_alter_table('page_insights', schema=None) as batch_op:
        # batch_op.drop_index('idx_page_insights_platform')
        batch_op.create_index(batch_op.f('ix_page_insights_platform'), ['platform'], unique=False)

    # System State
    with op.batch_alter_table('system_state', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_state_id'), ['id'], unique=False)

    # Viral Materials
    with op.batch_alter_table('viral_materials', schema=None) as batch_op:
        # batch_op.drop_index('ix_viral_materials_url')
        batch_op.create_index(batch_op.f('ix_viral_materials_url'), ['url'], unique=True)
        batch_op.create_index(batch_op.f('ix_viral_materials_id'), ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema - Minimalist version."""
    # Viral Materials
    with op.batch_alter_table('viral_materials', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_viral_materials_id'))
        batch_op.drop_index(batch_op.f('ix_viral_materials_url'))
        batch_op.create_index('ix_viral_materials_url', ['url'], unique=False)

    # System State
    with op.batch_alter_table('system_state', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_system_state_id'))

    # Page Insights
    with op.batch_alter_table('page_insights', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_page_insights_platform'))
        batch_op.create_index('idx_page_insights_platform', ['platform'], unique=False)

    # Jobs
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_tracking_code'))
        batch_op.drop_index(batch_op.f('ix_jobs_status'))
        batch_op.drop_index(batch_op.f('ix_jobs_scheduled_at'))
        batch_op.drop_index(batch_op.f('ix_jobs_last_metrics_check_ts'))
        batch_op.drop_index(batch_op.f('ix_jobs_last_heartbeat_at'))
        batch_op.drop_index(batch_op.f('ix_jobs_finished_at'))
        batch_op.drop_index(batch_op.f('ix_jobs_dedupe_key'))
        batch_op.drop_index(batch_op.f('ix_jobs_batch_id'))
        batch_op.create_index('idx_jobs_tracking', ['tracking_code'], unique=False)
        batch_op.create_index('idx_jobs_scheduled', ['scheduled_at'], unique=False)
        batch_op.create_index('idx_jobs_last_metrics_check', ['last_metrics_check_ts'], unique=False)

    # Discovered Channels
    with op.batch_alter_table('discovered_channels', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_discovered_channels_id'))
        batch_op.create_index('ix_discovered_channels_url_acc', ['channel_url', 'account_id'], unique=1)
        batch_op.create_index('ix_discovered_channels_account_id', ['account_id'], unique=False)

    # Accounts
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_constraint('uq_accounts_profile_path', type_='unique')
        batch_op.drop_index(batch_op.f('ix_accounts_login_status'))
        batch_op.drop_index(batch_op.f('ix_accounts_is_active'))
        batch_op.create_index('idx_accounts_profile', ['profile_path'], unique=1)

    # ### end Alembic commands ###
