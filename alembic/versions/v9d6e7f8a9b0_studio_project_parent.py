"""PLAN-106 P4.2 — studio_projects.parent_project_id: biến thể A/B trỏ về dự án gốc.

Revision ID: v9d6e7f8a9b0
Revises: u8c5d6e7f8a9
Create Date: 2026-10-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v9d6e7f8a9b0"
down_revision = "u8c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("studio_projects", sa.Column("parent_project_id", sa.Integer(), nullable=True))
    op.create_index("ix_studio_projects_parent_project_id", "studio_projects", ["parent_project_id"])


def downgrade() -> None:
    op.drop_index("ix_studio_projects_parent_project_id", table_name="studio_projects")
    op.drop_column("studio_projects", "parent_project_id")
