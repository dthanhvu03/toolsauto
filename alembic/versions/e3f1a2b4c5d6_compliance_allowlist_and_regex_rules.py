"""compliance allowlist + regex rules (DB-driven)

Revision ID: e3f1a2b4c5d6
Revises: d7b2e4a91c0f
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f1a2b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d7b2e4a91c0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_allowlist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("phrase", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phrase", name="uq_compliance_allowlist_phrase"),
    )
    op.create_index(
        "ix_compliance_allowlist_phrase",
        "compliance_allowlist",
        ["phrase"],
        unique=False,
    )

    op.create_table(
        "compliance_regex_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), server_default="WARNING", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pattern", name="uq_compliance_regex_rules_pattern"),
    )

    conn = op.get_bind()

    allow_rows = [
        ("trị giá", "seed"),
        ("miễn phí ship", "seed"),
        ("freeship", "seed"),
        ("flash sale", "seed"),
        ("deal hot", "seed"),
    ]
    for phrase, src in allow_rows:
        conn.execute(
            sa.text(
                "INSERT OR IGNORE INTO compliance_allowlist (phrase, is_active, source, created_at) "
                "VALUES (:p, 1, :s, CAST(strftime('%s','now') AS INTEGER))"
            ),
            {"p": phrase, "s": src},
        )

    regex_rows = [
        (
            r"[!?]{3,}",
            "Dấu câu lặp lại (!!!, ???)",
            "WARNING",
            0,
        ),
        (
            r"[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯ]{5,}",
            "Chữ IN HOA quá nhiều",
            "WARNING",
            1,
        ),
        (
            r"[\U0001F300-\U0001FFFF]{6,}",
            "Quá nhiều emoji liên tiếp",
            "WARNING",
            2,
        ),
        (
            r"(#\w+\s*){6,}",
            "Quá nhiều hashtag",
            "WARNING",
            3,
        ),
        (
            r"(.{15,})\1{2,}",
            "Lặp lại nội dung",
            "WARNING",
            4,
        ),
    ]
    for pat, desc, sev, so in regex_rows:
        conn.execute(
            sa.text(
                "INSERT OR IGNORE INTO compliance_regex_rules "
                "(pattern, description, severity, is_active, sort_order, created_at) "
                "VALUES (:pat, :desc, :sev, 1, :so, CAST(strftime('%s','now') AS INTEGER))"
            ),
            {"pat": pat, "desc": desc, "sev": sev, "so": so},
        )


def downgrade() -> None:
    op.drop_table("compliance_regex_rules")
    op.drop_index("ix_compliance_allowlist_phrase", table_name="compliance_allowlist")
    op.drop_table("compliance_allowlist")
