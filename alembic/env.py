"""Alembic environment: uses DATABASE_URL from app.config and SQLAlchemy models metadata."""
from __future__ import annotations

import logging.config
import os
import sys

from alembic import context

# Project root on sys.path (alembic.ini has prepend_sys_path = .)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import DATABASE_URL
from app.database.core import Base, engine
import app.database.models  # noqa: F401 — register all models on Base.metadata

config = context.config
target_metadata = Base.metadata

if config.config_file_name is not None:
    logging.config.fileConfig(config.config_file_name)


def _sqlite_batch() -> bool:
    return DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_sqlite_batch(),
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_sqlite_batch(),
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
