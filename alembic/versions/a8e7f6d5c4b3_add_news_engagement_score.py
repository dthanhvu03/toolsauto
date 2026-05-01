"""add engagement_score to news_articles

Revision ID: a8e7f6d5c4b3
Revises: 9f1c2d3e4a5b
Create Date: 2026-05-01 12:00:00.000000

"""
from __future__ import annotations

import time
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8e7f6d5c4b3"
down_revision: Union[str, Sequence[str], None] = "9f1c2d3e4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SETTINGS_SEED = (
    ("THREADS_SOURCE_WEIGHTS", "{}", "text"),
)


def _seed_runtime_settings(conn) -> None:
    inspector = sa.inspect(conn)
    if not inspector.has_table("runtime_settings"):
        return

    runtime_settings = sa.table(
        "runtime_settings",
        sa.column("key", sa.String()),
        sa.column("value", sa.String()),
        sa.column("type", sa.String()),
        sa.column("updated_at", sa.Integer()),
        sa.column("updated_by", sa.String()),
    )
    target_keys = [seed[0] for seed in _SETTINGS_SEED]
    existing_keys = {
        row[0]
        for row in conn.execute(
            sa.select(runtime_settings.c.key).where(runtime_settings.c.key.in_(target_keys))
        )
    }

    now_ts = int(time.time())
    for key, value, value_type in _SETTINGS_SEED:
        if key in existing_keys:
            continue
        conn.execute(
            runtime_settings.insert().values(
                key=key,
                value=value,
                type=value_type,
                updated_at=now_ts,
                updated_by="alembic_PLAN_034",
            )
        )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("news_articles"):
        return

    column_names = {column["name"] for column in inspector.get_columns("news_articles")}
    if "engagement_score" not in column_names:
        with op.batch_alter_table("news_articles") as batch_op:
            batch_op.add_column(sa.Column("engagement_score", sa.Float(), nullable=True))

    inspector = sa.inspect(conn)
    index_names = {index["name"] for index in inspector.get_indexes("news_articles")}
    score_index = op.f("ix_news_articles_engagement_score")
    if score_index not in index_names:
        with op.batch_alter_table("news_articles") as batch_op:
            batch_op.create_index(score_index, ["engagement_score"], unique=False)

    _seed_runtime_settings(conn)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("news_articles"):
        return

    index_names = {index["name"] for index in inspector.get_indexes("news_articles")}
    score_index = op.f("ix_news_articles_engagement_score")
    with op.batch_alter_table("news_articles") as batch_op:
        if score_index in index_names:
            batch_op.drop_index(score_index)
        column_names = {column["name"] for column in inspector.get_columns("news_articles")}
        if "engagement_score" in column_names:
            batch_op.drop_column("engagement_score")
