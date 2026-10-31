"""PLAN-109 — DocType kiểu Frappe: bảng doctypes + doc_records (chỉ thêm).

Revision ID: w0e7f8a9b0c1
Revises: v9d6e7f8a9b0
Create Date: 2026-10-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "w0e7f8a9b0c1"
down_revision = "v9d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "doctypes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("module", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("is_child", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("title_field", sa.String(64), nullable=True),
        sa.Column("naming", sa.String(80), nullable=False, server_default="autoincrement"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("modified_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "doc_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctype", sa.String(64), nullable=False),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("modified_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("doctype", "name", name="uq_doc_records_doctype_name"),
    )
    op.create_index("ix_doc_records_doctype", "doc_records", ["doctype"])


def downgrade() -> None:
    op.drop_index("ix_doc_records_doctype", table_name="doc_records")
    op.drop_table("doc_records")
    op.drop_table("doctypes")
