"""p037_p3_facebook_adapter_path

Revision ID: 883c60c7be10
Revises: c7d9e1f2a3b4
Create Date: 2026-05-04 09:36:53.700213

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '883c60c7be10'
down_revision: Union[str, Sequence[str], None] = 'c7d9e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE platform_configs "
        "SET adapter_class = 'app.features.facebook.adapter.FacebookAdapter' "
        "WHERE adapter_class = 'app.adapters.facebook.adapter.FacebookAdapter'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE platform_configs "
        "SET adapter_class = 'app.adapters.facebook.adapter.FacebookAdapter' "
        "WHERE adapter_class = 'app.features.facebook.adapter.FacebookAdapter'"
    )
