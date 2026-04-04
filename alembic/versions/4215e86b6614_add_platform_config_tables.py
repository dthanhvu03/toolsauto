"""noop duplicate platform_config head (schema from 821e5a9d233c)

Revision ID: 4215e86b6614
Revises: 821e5a9d233c
Create Date: 2026-04-04 04:57:10.322222

Tables platform_configs, workflow_definitions, platform_selectors, and cta_templates
are already created by revision 821e5a9d233c. This file was a duplicate migration;
upgrade/downgrade are no-ops so `alembic upgrade head` succeeds on DBs that already
applied 821e5a9d233c.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "4215e86b6614"
down_revision: Union[str, Sequence[str], None] = "821e5a9d233c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
