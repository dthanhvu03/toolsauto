import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import settings as runtime_settings
from app.core.database.models import RuntimeSetting, RuntimeSettingAudit


@pytest.fixture
def settings_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    RuntimeSetting.__table__.create(engine)
    RuntimeSettingAudit.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(runtime_settings, "_cache_ts", 0.0)
    monkeypatch.setattr(runtime_settings, "_cache_values", {})
    monkeypatch.setitem(os.environ, "AI_CAPTION_STYLE", "")
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_caption_style_registry_defaults_to_short_and_is_studio_only():
    spec = runtime_settings.SETTINGS["ai.caption_style"]

    assert spec.type == "enum"
    assert spec.default_getter() == "short"
    assert spec.choices == ["short", "conversation", "daily", "humor", "sales", "general"]
    assert spec.studio_only is True


def test_caption_style_default_and_db_overrides(settings_db):
    assert runtime_settings.get_str("ai.caption_style", default="missing", db=settings_db) == "short"

    runtime_settings.upsert_setting(
        settings_db, "ai.caption_style", "conversation", updated_by="test"
    )
    assert runtime_settings.get_str("ai.caption_style", db=settings_db) == "conversation"

    runtime_settings.upsert_setting(
        settings_db, "ai.caption_style", "daily", updated_by="test"
    )
    assert runtime_settings.get_str("ai.caption_style", db=settings_db) == "daily"


def test_caption_style_rejects_invalid_override_without_changing_value(settings_db):
    runtime_settings.upsert_setting(
        settings_db, "ai.caption_style", "daily", updated_by="test"
    )

    with pytest.raises(ValueError, match="Invalid choice"):
        runtime_settings.upsert_setting(
            settings_db, "ai.caption_style", "invented-style", updated_by="test"
        )

    assert runtime_settings.get_str("ai.caption_style", db=settings_db) == "daily"
