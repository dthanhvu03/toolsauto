"""add topic_key to news_articles

Revision ID: 9f1c2d3e4a5b
Revises: c9d0e1f2a3b4
Create Date: 2026-04-28 11:30:00.000000

"""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f1c2d3e4a5b"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "va",
    "la",
    "cua",
    "trong",
    "tai",
    "cho",
    "voi",
    "da",
    "se",
    "mot",
    "cac",
    "nhung",
    "nay",
    "do",
    "khi",
    "sau",
    "truoc",
    "theo",
    "de",
    "ra",
    "vao",
    "len",
    "xuong",
    "co",
    "khong",
    "tong",
    "thong",
    "lenh",
    "moi",
    "tren",
}
_SETTINGS_SEED = (
    ("THREADS_MAX_ARTICLE_AGE_HOURS", "6", "int"),
    ("THREADS_TOPIC_DEDUP_HOURS", "24", "int"),
    ("THREADS_ACCOUNT_CATEGORY_MAP", "{}", "text"),
)


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").lower())
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.replace("\u0111", "d")


def _compute_topic_key(title: str) -> str:
    normalized_title = _normalize_text(title)
    keywords: list[str] = []
    seen: set[str] = set()

    for token in _TOKEN_RE.findall(normalized_title):
        if len(token) < 3 or token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)

    ranked = sorted(keywords, key=lambda token: (-len(token), token))[:7]
    payload = "|".join(sorted(ranked)) if ranked else normalized_title.strip() or "empty"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


def _backfill_topic_keys(conn) -> None:
    news_articles = sa.table(
        "news_articles",
        sa.column("id", sa.Integer()),
        sa.column("title", sa.String()),
        sa.column("topic_key", sa.String()),
    )
    rows = conn.execute(
        sa.select(news_articles.c.id, news_articles.c.title).where(
            sa.or_(news_articles.c.topic_key.is_(None), news_articles.c.topic_key == "")
        )
    ).fetchall()

    for start in range(0, len(rows), 500):
        for row in rows[start:start + 500]:
            conn.execute(
                news_articles.update()
                .where(news_articles.c.id == row.id)
                .values(topic_key=_compute_topic_key(row.title or ""))
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
                updated_by="alembic_PLAN_033",
            )
        )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("news_articles"):
        return

    column_names = {column["name"] for column in inspector.get_columns("news_articles")}
    if "topic_key" not in column_names:
        with op.batch_alter_table("news_articles") as batch_op:
            batch_op.add_column(sa.Column("topic_key", sa.String(), nullable=True))

    inspector = sa.inspect(conn)
    index_names = {index["name"] for index in inspector.get_indexes("news_articles")}
    topic_key_index = op.f("ix_news_articles_topic_key")
    if topic_key_index not in index_names:
        with op.batch_alter_table("news_articles") as batch_op:
            batch_op.create_index(topic_key_index, ["topic_key"], unique=False)

    _backfill_topic_keys(conn)
    _seed_runtime_settings(conn)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("news_articles"):
        return

    index_names = {index["name"] for index in inspector.get_indexes("news_articles")}
    topic_key_index = op.f("ix_news_articles_topic_key")
    with op.batch_alter_table("news_articles") as batch_op:
        if topic_key_index in index_names:
            batch_op.drop_index(topic_key_index)
        column_names = {column["name"] for column in inspector.get_columns("news_articles")}
        if "topic_key" in column_names:
            batch_op.drop_column("topic_key")
