"""P0-3: Owner/UI cannot save cooldown=0 or max_concurrent=10."""
from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import (
    MAX_CONCURRENT_ACCOUNTS_MAX,
    MIN_DELAY_BETWEEN_POSTS,
    POST_DELAY_MIN_FLOOR,
)
from app.core import settings as runtime_settings
from app.core.account import AccountService
from app.core.database.models import Account, Base
from app.core.queue.queue import QueueService
from app.platform.admin_api.mutations import AccountCreateBody


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    runtime_settings._cache_ts = 0.0
    runtime_settings._cache_values = {}
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        runtime_settings._cache_ts = 0.0
        runtime_settings._cache_values = {}


def test_settings_spec_hard_floors():
    conc = runtime_settings.SETTINGS["publish.max_concurrent_accounts"]
    assert conc.min == 1
    assert conc.max == MAX_CONCURRENT_ACCOUNTS_MAX == 2
    dmin = runtime_settings.SETTINGS["publish.delay_min_sec"]
    dmax = runtime_settings.SETTINGS["publish.delay_max_sec"]
    assert dmin.min == POST_DELAY_MIN_FLOOR == 30
    assert dmax.min == POST_DELAY_MIN_FLOOR == 30


def test_settings_reject_concurrent_5(db):
    with pytest.raises(ValueError, match="must be <= 2"):
        runtime_settings.upsert_setting(db, "publish.max_concurrent_accounts", "5")


def test_settings_reject_delay_min_0(db):
    with pytest.raises(ValueError, match="must be >= 30"):
        runtime_settings.upsert_setting(db, "publish.delay_min_sec", "0")


def test_settings_accept_concurrent_2(db):
    assert runtime_settings.upsert_setting(db, "publish.max_concurrent_accounts", "2") == 2


def test_account_update_rejects_cooldown_0(db):
    acc = Account(name="floor-acc", platform="facebook", cooldown_seconds=1800, daily_limit=3)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    with pytest.raises(ValueError, match="1800"):
        AccountService.update_limits(db, acc.id, daily_limit=3, cooldown_seconds=0)


def test_account_create_rejects_cooldown_0(db, tmp_path, monkeypatch):
    monkeypatch.setattr(AccountService, "BASE_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setattr(AccountService, "ensure_base_dir", classmethod(lambda cls: None))
    with pytest.raises(ValueError, match="1800"):
        AccountService.create_account(db, platform="facebook", name="no-zero", cooldown_seconds=0)


def test_account_api_body_rejects_cooldown_0():
    with pytest.raises(ValidationError):
        AccountCreateBody(name="x", cooldown_seconds=0)


def test_assert_cooldown_accepts_1800():
    assert AccountService.assert_cooldown_seconds(1800) == 1800
    assert AccountService.assert_cooldown_seconds(14400) == 14400


def test_claim_sql_uses_cooldown_floor():
    src = inspect.getsource(QueueService.claim_next_job)
    assert "GREATEST(a.cooldown_seconds, :min_cooldown)" in src
    assert "MIN_DELAY_BETWEEN_POSTS" in src or "min_cooldown" in src
    assert MIN_DELAY_BETWEEN_POSTS == 1800
