"""
ADR-017 — cửa vào "dán link" đa nền tảng.

- ``detect_platform`` / ``normalize_source_url``: bảng URL thuần.
- ``ViralService.add_material_from_url``: từ chối domain lạ, từ chối trùng, tạo NEW đúng platform.
- ``POST /viral/add-link``: toast + chỉ tạo task nền khi ``process_now``.

DB SQLite tạm + app FastAPI tối thiểu (bỏ auth middleware) như tests/test_viral_router_background.py.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import ViralStatus
from app.core.database.core import get_db
from app.core.database.models import Account, Job, ViralMaterial
from app.features.viral_intake import router as viral_router
from app.features.viral_intake.intake import detect_platform, normalize_source_url
from app.features.viral_intake.service import ViralService

# ── detect / normalize ───────────────────────────────────────────────────────

DETECT_TABLE = [
    ("https://www.tiktok.com/@user/video/7300000000000000001", "tiktok"),
    ("https://vt.tiktok.com/ZSabc123/", "tiktok"),
    ("https://vm.tiktok.com/ZMabc123/", "tiktok"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ?si=abc", "youtube"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share", "youtube"),
    ("https://youtu.be/dQw4w9WgXcQ?si=xyz", "youtube"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://www.facebook.com/reel/123456789", "facebook"),
    ("https://www.facebook.com/watch/?v=123456789", "facebook"),
    ("https://fb.watch/abcDEF/", "facebook"),
    ("https://www.facebook.com/share/r/abcDEF/", "facebook"),
    ("https://www.instagram.com/reel/Cabc123/?igsh=xyz", "instagram"),
    ("https://www.instagram.com/p/Cabc123/", "instagram"),
    ("tiktok.com/@user/video/1", "tiktok"),  # thiếu scheme vẫn nhận
    # từ chối
    ("https://www.youtube.com/@somechannel", None),
    ("https://www.youtube.com/watch", None),
    ("https://www.facebook.com/somepage", None),
    ("https://www.instagram.com/someuser/", None),
    ("https://v.douyin.com/abc/", None),
    ("https://example.com/video/1", None),
    ("not a url", None),
    ("", None),
]


@pytest.mark.parametrize("url,expected", DETECT_TABLE)
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


NORMALIZE_TABLE = [
    (
        "https://www.youtube.com/shorts/dQw4w9WgXcQ?si=abc",
        "https://youtube.com/shorts/dQw4w9WgXcQ",
    ),
    (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share&list=PL1&t=10s",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
    ),
    ("https://youtu.be/dQw4w9WgXcQ?si=xyz", "https://youtu.be/dQw4w9WgXcQ"),
    (
        "https://www.tiktok.com/@user/video/730?_r=1&_t=abc&is_from_webapp=1&utm_source=x",
        "https://tiktok.com/@user/video/730",
    ),
    ("https://vt.tiktok.com/ZSabc123/", "https://vt.tiktok.com/ZSabc123"),
    ("https://www.facebook.com/watch/?v=123&fbclid=zzz", "https://facebook.com/watch?v=123"),
    ("https://www.facebook.com/reel/123/?mibextid=abc", "https://facebook.com/reel/123"),
    ("https://www.instagram.com/reel/Cabc123/?igsh=xyz#frag", "https://instagram.com/reel/Cabc123"),
    ("  https://m.facebook.com/reel/123/  ", "https://facebook.com/reel/123"),
    ("http://www.instagram.com/p/Cabc123", "https://instagram.com/p/Cabc123"),
    # query hữu ích không phải tracking thì giữ, và sắp xếp ổn định
    ("https://example.com/x?b=2&a=1&utm_medium=m", "https://example.com/x?a=1&b=2"),
    ("", ""),
]


@pytest.mark.parametrize("url,expected", NORMALIZE_TABLE)
def test_normalize_source_url(url, expected):
    assert normalize_source_url(url) == expected


def test_normalize_is_idempotent():
    for url, _ in NORMALIZE_TABLE:
        once = normalize_source_url(url)
        assert normalize_source_url(once) == once


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'viral_intake.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def client(session_factory, monkeypatch):
    app = FastAPI()
    app.include_router(viral_router.router)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(viral_router, "SessionLocal", session_factory)
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: True))
    return TestClient(app)


@pytest.fixture
def bg_calls(monkeypatch):
    """Thay task nền bằng bản ghi lại — không chạy yt-dlp/ffmpeg thật."""
    recorded: list[int] = []
    monkeypatch.setattr(
        viral_router, "_process_material_in_background", lambda material_id: recorded.append(material_id)
    )
    return recorded


def _triggers(resp) -> dict:
    return json.loads(resp.headers["HX-Trigger"])


YT_SHORT = "https://www.youtube.com/shorts/dQw4w9WgXcQ?si=abc"


# ── service: add_material_from_url ───────────────────────────────────────────


def test_add_rejects_unknown_domain(session_factory):
    with session_factory() as db:
        ok, msg, mid = ViralService.add_material_from_url(db, "https://example.com/video/1")
        assert (ok, mid) == (False, None)
        assert "Không nhận diện được nền tảng" in msg
        assert db.query(ViralMaterial).count() == 0


@pytest.mark.parametrize(
    "url,platform,stored",
    [
        (YT_SHORT, "youtube", "https://youtube.com/shorts/dQw4w9WgXcQ"),
        ("https://vt.tiktok.com/ZSabc123/", "tiktok", "https://vt.tiktok.com/ZSabc123"),
        ("https://www.facebook.com/reel/123/?fbclid=x", "facebook", "https://facebook.com/reel/123"),
        ("https://www.instagram.com/reel/Cabc/?igsh=x", "instagram", "https://instagram.com/reel/Cabc"),
    ],
)
def test_add_creates_new_material(session_factory, url, platform, stored):
    with session_factory() as db:
        ok, msg, mid = ViralService.add_material_from_url(db, url, target_page="  ")
        assert ok is True and mid
        assert msg == f"Đã thêm #{mid} ({platform})"

        mat = db.get(ViralMaterial, mid)
        assert mat.platform == platform
        assert mat.url == stored
        assert mat.status == ViralStatus.NEW
        assert mat.views == 0
        assert mat.title == ""
        assert mat.scraped_by_account_id is None
        assert mat.target_page is None  # chuỗi trống → None


def test_add_keeps_target_page(session_factory):
    with session_factory() as db:
        ok, _, mid = ViralService.add_material_from_url(
            db, YT_SHORT, target_page="https://facebook.com/mypage"
        )
        assert ok
        assert db.get(ViralMaterial, mid).target_page == "https://facebook.com/mypage"


def test_add_rejects_duplicate_after_normalization(session_factory):
    with session_factory() as db:
        ok, _, first_id = ViralService.add_material_from_url(db, YT_SHORT)
        assert ok
        db.get(ViralMaterial, first_id).status = ViralStatus.DRAFTED
        db.commit()

        ok2, msg2, dup_id = ViralService.add_material_from_url(
            db, "https://youtube.com/shorts/dQw4w9WgXcQ/?feature=share"
        )
        assert ok2 is False
        assert dup_id == first_id
        assert msg2 == f"#{first_id} đã có (trạng thái DRAFTED)"
        assert db.query(ViralMaterial).count() == 1


# ── endpoint: POST /viral/add-link ───────────────────────────────────────────


def test_add_link_without_process_now_only_creates(client, session_factory, bg_calls):
    resp = client.post("/viral/add-link", data={"url": YT_SHORT})

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "success"
    assert trig["showMessage"]["msg"].startswith("Đã thêm #")
    assert "(youtube)" in trig["showMessage"]["msg"]
    assert trig["refreshViralTable"] is True
    assert "viralBackgroundStarted" not in trig
    assert bg_calls == []

    with session_factory() as db:
        mats = db.query(ViralMaterial).all()
        assert len(mats) == 1
        assert mats[0].url == "https://youtube.com/shorts/dQw4w9WgXcQ"
        assert mats[0].status == ViralStatus.NEW


def test_add_link_with_process_now_queues_background(client, session_factory, bg_calls):
    resp = client.post(
        "/viral/add-link",
        data={"url": YT_SHORT, "process_now": "true", "target_page": "https://facebook.com/p1"},
    )

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "success"
    assert "đang xử lý nền" in trig["showMessage"]["msg"]
    assert trig["viralBackgroundStarted"] is True
    assert trig["refreshViralTable"] is True

    with session_factory() as db:
        mat = db.query(ViralMaterial).one()
        assert mat.target_page == "https://facebook.com/p1"
    # TestClient chạy xong task nền trước khi trả response → đúng 1 lần với đúng id.
    assert bg_calls == [mat.id]


def test_add_link_rejects_unknown_domain_with_error_toast(client, session_factory, bg_calls):
    resp = client.post("/viral/add-link", data={"url": "https://example.com/v/1", "process_now": "true"})

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "error"
    assert "Không nhận diện được nền tảng" in trig["showMessage"]["msg"]
    assert "viralBackgroundStarted" not in trig
    assert bg_calls == []
    with session_factory() as db:
        assert db.query(ViralMaterial).count() == 0


def test_add_link_rejects_duplicate_without_background(client, session_factory, bg_calls):
    first = _triggers(client.post("/viral/add-link", data={"url": YT_SHORT}))
    assert first["showMessage"]["type"] == "success"

    # cùng video, khác query/www → vẫn trùng sau chuẩn hoá
    dup = _triggers(client.post("/viral/add-link", data={"url": YT_SHORT.split("?")[0], "process_now": "true"}))

    assert dup["showMessage"]["type"] == "error"
    assert "đã có (trạng thái NEW)" in dup["showMessage"]["msg"]
    assert "viralBackgroundStarted" not in dup
    assert bg_calls == []
    with session_factory() as db:
        assert db.query(ViralMaterial).count() == 1


def test_add_link_process_now_without_ffmpeg_creates_but_does_not_queue(client, session_factory, bg_calls, monkeypatch):
    monkeypatch.setattr(ViralService, "ffmpeg_available", staticmethod(lambda: False))

    trig = _triggers(client.post("/viral/add-link", data={"url": YT_SHORT, "process_now": "true"}))

    assert trig["showMessage"]["type"] == "error"
    assert "Đã thêm #" in trig["showMessage"]["msg"] and "ffmpeg" in trig["showMessage"]["msg"]
    assert "viralBackgroundStarted" not in trig
    assert bg_calls == []
    with session_factory() as db:
        assert db.query(ViralMaterial).count() == 1  # material vẫn được giữ, chỉ chưa xử lý
