"""add_platform_config_tables

Revision ID: 821e5a9d233c
Revises: f1a2b3c4d5e7
Create Date: 2026-04-04 04:49:29.180451

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '821e5a9d233c'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "platform_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("adapter_class", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("display_emoji", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("base_urls", sa.Text(), nullable=True),
        sa.Column("viewport", sa.Text(), nullable=True),
        sa.Column("user_agents", sa.Text(), nullable=True),
        sa.Column("browser_args", sa.Text(), nullable=True),
        sa.Column("media_extensions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", name="uq_platform_configs_platform"),
    )

    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("steps", sa.Text(), nullable=True),
        sa.Column("timing_config", sa.Text(), nullable=True),
        sa.Column("retry_config", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_workflow_definitions_name"),
    )
    op.create_index(
        "ix_workflow_platform_jobtype",
        "workflow_definitions",
        ["platform", "job_type"],
    )

    op.create_table(
        "platform_selectors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("selector_name", sa.String(), nullable=False),
        sa.Column("selector_type", sa.String(), server_default="css", nullable=True),
        sa.Column("selector_value", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(), server_default="*", nullable=True),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=True),
        sa.Column("valid_from", sa.Integer(), nullable=True),
        sa.Column("valid_until", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_selectors_lookup",
        "platform_selectors",
        ["platform", "category", "is_active"],
    )

    op.create_table(
        "cta_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(), server_default="vi", nullable=True),
        sa.Column("page_url", sa.String(), nullable=True),
        sa.Column("niche", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cta_templates_platform",
        "cta_templates",
        ["platform", "is_active"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_cta_templates_platform", table_name="cta_templates")
    op.drop_table("cta_templates")
    op.drop_index("ix_platform_selectors_lookup", table_name="platform_selectors")
    op.drop_table("platform_selectors")
    op.drop_index("ix_workflow_platform_jobtype", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
    op.drop_table("platform_configs")
