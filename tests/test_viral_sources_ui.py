"""
ADR-019 — router + template "Nguồn tự động" (/viral/sources…).

Backend (``app/features/viral_intake/sources.py``) làm song song theo hợp đồng ADR-019 mục 2,
nên test này KHÔNG phụ thuộc nó: gắn ``SourceService`` giả vào ``sys.modules`` (router import
lười trong hàm) và ghi lại mọi lời gọi. App FastAPI tối thiểu + SQLite tạm như
tests/test_viral_router_background.py.
"""
from __future__ import annotations

import json
import re
import sys
import time
import types
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database.core import get_db
from app.features.viral_intake import router as viral_router

SOURCES_MODULE = "app.features.viral_intake.sources"


def _source(**over) -> SimpleNamespace:
    """Object giả đủ attribute ADR-019 mục 1."""
    base = dict(
        id=1, platform="tiktok", url="https://tiktok.com/@brandshop", handle="brandshop",
        min_views=50000, max_videos=20, target_page="https://facebook.com/mypage", enabled=True,
        last_scanned_at=int(time.time()) - 5 * 60, last_found=7, last_error=None,
        created_at=0, updated_at=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


SOURCES = [
    _source(),
    _source(
        id=2, platform="youtube", url="https://youtube.com/@somebrand/shorts", handle="somebrand",
        min_views=None, max_videos=None, target_page=None, enabled=False,
        last_scanned_at=None, last_found=None,
        last_error="ERROR: [youtube] Unable to download webpage: HTTP Error 429 — Too Many Requests",
    ),
]


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'viral_sources_ui.sqlite'}")
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def fake_service(monkeypatch):
    """SourceService giả theo đúng chữ ký hợp đồng; ``calls`` ghi lại (tên, db, *args, kwargs)."""
    calls: list[tuple] = []
    state = {"sources": list(SOURCES), "raise": None}

    class FakeSourceService:
        @staticmethod
        def list_sources(db):
            calls.append(("list_sources", db))
            if state["raise"] == "list_sources":
                raise RuntimeError("db down")
            return state["sources"]

        @staticmethod
        def add_source(db, url, *, min_views=None, max_videos=None, target_page=None):
            calls.append(("add_source", db, url, dict(min_views=min_views, max_videos=max_videos, target_page=target_page)))
            if state["raise"] == "add_source":
                raise RuntimeError("yt-dlp missing")
            if "facebook.com" in url:
                return False, "Facebook/Instagram không liệt kê được kênh — chỉ dán từng link video.", None
            return True, "Đã thêm nguồn #3 (tiktok @newshop)", 3

        @staticmethod
        def set_enabled(db, source_id, enabled):
            calls.append(("set_enabled", db, source_id, enabled))
            if state["raise"] == "set_enabled":
                raise RuntimeError("locked")
            return source_id in {s.id for s in state["sources"]}

        @staticmethod
        def delete_source(db, source_id):
            calls.append(("delete_source", db, source_id))
            if state["raise"] == "delete_source":
                raise RuntimeError("locked")
            return source_id in {s.id for s in state["sources"]}

        @staticmethod
        def scan_source(db, source):
            calls.append(("scan_source", db, source))
            if state["raise"] == "scan_source":
                raise RuntimeError("yt-dlp exploded")
            return 3, 1, None

        @staticmethod
        def scan_all(db, *, only_due=True):
            calls.append(("scan_all", db, dict(only_due=only_due)))
            if state["raise"] == "scan_all":
                raise RuntimeError("yt-dlp exploded")
            return {"found": 3, "scanned": 2, "errors": 0}

    mod = sys.modules.get(SOURCES_MODULE)
    if mod is None:
        mod = types.ModuleType(SOURCES_MODULE)
        monkeypatch.setitem(sys.modules, SOURCES_MODULE, mod)
    monkeypatch.setattr(mod, "SourceService", FakeSourceService, raising=False)
    return SimpleNamespace(calls=calls, state=state)


@pytest.fixture
def client(session_factory, monkeypatch, fake_service):
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
    return TestClient(app)


def _triggers(resp) -> dict:
    return json.loads(resp.headers["HX-Trigger"])


def _names(calls) -> list[str]:
    return [c[0] for c in calls]


# ── GET /viral/sources ───────────────────────────────────────────────────────


def test_fragment_renders_every_column_for_two_sources(client, fake_service):
    resp = client.get("/viral/sources")

    assert resp.status_code == 200
    # bỏ khoảng trắng/xuống dòng quanh thẻ để assert ">20<" không phụ thuộc indent template
    html = re.sub(r"\s*([<>])\s*", r"\1", re.sub(r"\s+", " ", resp.text))
    assert _names(fake_service.calls) == ["list_sources"]
    assert isinstance(fake_service.calls[0][1], Session)

    # header
    for col in ["Nền tảng", "Kênh", "Min views", "Max video", "Page đích", "Bật", "Quét cuối", "Tìm thấy", "Lỗi", "Thao tác"]:
        assert col in html
    # nguồn 1: đủ dữ liệu
    assert 'id="viral-source-1"' in html and 'id="viral-source-2"' in html
    assert "TikTok" in html and "YouTube" in html
    assert "@brandshop" in html and "@somebrand" in html
    assert "50,000" in html and ">20<" in html
    assert "https://facebook.com/mypage" in html
    assert "5 phút trước" in html and ">7<" in html
    # nguồn 2: null → mặc định / — / Chưa quét, lỗi rút gọn + tooltip đầy đủ
    assert html.count("mặc định") >= 2
    assert "Chưa quét" in html
    assert 'title="ERROR: [youtube] Unable to download webpage: HTTP Error 429 — Too Many Requests"' in html
    assert "HTTP Error 429 — Too Many Requests</span>" not in html  # đã cắt ngắn
    # điều khiển htmx
    assert 'hx-post="/viral/sources/1/toggle"' in html and 'hx-post="/viral/sources/2/toggle"' in html
    assert 'hx-post="/viral/sources/1/scan"' in html
    assert 'hx-post="/viral/sources/2/delete"' in html and "hx-confirm=" in html
    # checkbox: nguồn 1 bật (attribute `checked` ngay trước hx-post), nguồn 2 tắt + hàng mờ
    assert 'checked hx-post="/viral/sources/1/toggle"' in html
    assert 'checked hx-post="/viral/sources/2/toggle"' not in html
    row1 = html.split('id="viral-source-1"')[1].split('id="viral-source-2"')[0]
    row2 = html.split('id="viral-source-2"')[1]
    assert "opacity-60" in row2 and "opacity-60" not in row1


def test_fragment_empty_shows_guidance(client, fake_service):
    fake_service.state["sources"] = []

    html = client.get("/viral/sources").text

    assert "Chưa có nguồn nào" in html
    assert "tiktok.com/@kenh" in html and "youtube.com/@kenh" in html
    assert "viral-source-" not in html


def test_fragment_survives_service_error(client, fake_service):
    fake_service.state["raise"] = "list_sources"

    resp = client.get("/viral/sources")

    assert resp.status_code == 200
    assert "Chưa có nguồn nào" in resp.text


# ── POST /viral/sources/add ──────────────────────────────────────────────────


def test_add_passes_parameters_and_toasts(client, fake_service):
    resp = client.post(
        "/viral/sources/add",
        data={"url": "https://tiktok.com/@newshop", "min_views": "20000", "max_videos": "15", "target_page": " https://facebook.com/p1 "},
    )

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"] == {"msg": "Đã thêm nguồn #3 (tiktok @newshop)", "type": "success"}
    assert trig["refreshViralSources"] is True
    name, db, url, kw = fake_service.calls[0]
    assert name == "add_source" and isinstance(db, Session)
    assert url == "https://tiktok.com/@newshop"
    assert kw == {"min_views": 20000, "max_videos": 15, "target_page": "https://facebook.com/p1"}


def test_add_empty_optional_fields_become_none(client, fake_service):
    client.post("/viral/sources/add", data={"url": "https://tiktok.com/@newshop", "min_views": "", "max_videos": "", "target_page": ""})

    assert fake_service.calls[0][3] == {"min_views": None, "max_videos": None, "target_page": None}


def test_add_rejection_from_service_is_error_toast(client, fake_service):
    trig = _triggers(client.post("/viral/sources/add", data={"url": "https://facebook.com/somepage"}))

    assert trig["showMessage"]["type"] == "error"
    assert "chỉ dán từng link video" in trig["showMessage"]["msg"]
    assert trig["refreshViralSources"] is True


def test_add_service_exception_is_error_toast_not_500(client, fake_service):
    fake_service.state["raise"] = "add_source"

    resp = client.post("/viral/sources/add", data={"url": "https://tiktok.com/@x"})

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "error"
    assert "yt-dlp missing" in trig["showMessage"]["msg"]


# ── toggle / delete ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("sent,expected", [("true", True), ("false", False), (None, False)])
def test_toggle_calls_set_enabled(client, fake_service, sent, expected):
    data = {} if sent is None else {"enabled": sent}

    trig = _triggers(client.post("/viral/sources/1/toggle", data=data))

    assert trig["showMessage"]["type"] == "success"
    assert ("bật" if expected else "tắt") in trig["showMessage"]["msg"]
    assert trig["refreshViralSources"] is True
    name, db, sid, enabled = fake_service.calls[0]
    assert (name, sid, enabled) == ("set_enabled", 1, expected)
    assert isinstance(db, Session)


def test_toggle_unknown_id_is_error_toast(client, fake_service):
    trig = _triggers(client.post("/viral/sources/999/toggle", data={"enabled": "true"}))

    assert trig["showMessage"]["type"] == "error"
    assert "#999" in trig["showMessage"]["msg"]


def test_delete_calls_delete_source(client, fake_service):
    trig = _triggers(client.post("/viral/sources/2/delete"))

    assert trig["showMessage"]["type"] == "success"
    assert "#2" in trig["showMessage"]["msg"]
    assert trig["refreshViralSources"] is True
    assert [(c[0], c[2]) for c in fake_service.calls] == [("delete_source", 2)]


@pytest.mark.parametrize("endpoint,method", [("set_enabled", "toggle"), ("delete_source", "delete")])
def test_toggle_delete_service_exception_is_error_toast(client, fake_service, endpoint, method):
    fake_service.state["raise"] = endpoint

    resp = client.post(f"/viral/sources/1/{method}", data={"enabled": "true"})

    assert resp.status_code == 204
    assert _triggers(resp)["showMessage"]["type"] == "error"


# ── scan (nền) ───────────────────────────────────────────────────────────────


def test_scan_one_runs_scan_source_in_background_with_right_source(client, fake_service, monkeypatch):
    # Bắt add_task để khẳng định KHÔNG gọi đồng bộ trong handler, rồi tự chạy task.
    queued: list[tuple] = []
    original_add_task = viral_router.BackgroundTasks.add_task

    def spy_add_task(self, func, *args, **kwargs):
        queued.append((func, args, kwargs))
        return original_add_task(self, func, *args, **kwargs)

    monkeypatch.setattr(viral_router.BackgroundTasks, "add_task", spy_add_task)

    resp = client.post("/viral/sources/2/scan")

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "success"
    assert "Đang quét nền" in trig["showMessage"]["msg"]
    assert trig["refreshViralSources"] is True and trig["refreshViralTable"] is True
    assert queued == [(viral_router._scan_source_in_background, (2,), {})]
    # TestClient chạy task nền xong trước khi trả về → đã gọi list_sources + scan_source đúng nguồn #2.
    assert _names(fake_service.calls) == ["list_sources", "scan_source"]
    _, bg_db, source = fake_service.calls[1]
    assert source is SOURCES[1]
    assert isinstance(bg_db, Session)


def test_scan_one_not_called_synchronously(client, fake_service, monkeypatch):
    """Handler chỉ xếp task; bỏ task nền đi thì scan_source không được gọi."""
    monkeypatch.setattr(viral_router.BackgroundTasks, "add_task", lambda self, f, *a, **k: None)

    trig = _triggers(client.post("/viral/sources/1/scan"))

    assert trig["showMessage"]["type"] == "success"
    assert fake_service.calls == []


def test_scan_one_unknown_id_logs_and_skips(client, fake_service, caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger=viral_router.__name__):
        resp = client.post("/viral/sources/999/scan")

    assert resp.status_code == 204
    assert _names(fake_service.calls) == ["list_sources"]
    assert any("#999" in r.getMessage() for r in caplog.records)


def test_scan_all_runs_in_background_with_only_due_false(client, fake_service):
    # MonkeyPatch riêng: .undo() trên fixture monkeypatch sẽ gỡ luôn fake SourceService.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(viral_router.BackgroundTasks, "add_task", lambda self, f, *a, **k: None)
        trig = _triggers(client.post("/viral/sources/scan-all"))
    assert trig["showMessage"]["type"] == "success" and "Đang quét nền" in trig["showMessage"]["msg"]
    assert trig["refreshViralSources"] is True and trig["refreshViralTable"] is True
    assert fake_service.calls == []  # không đồng bộ

    client.post("/viral/sources/scan-all")
    assert [(c[0], c[2]) for c in fake_service.calls] == [("scan_all", {"only_due": False})]
    assert isinstance(fake_service.calls[0][1], Session)


@pytest.mark.parametrize("path,which", [("/viral/sources/1/scan", "scan_source"), ("/viral/sources/scan-all", "scan_all")])
def test_scan_background_failure_is_logged_not_swallowed(client, fake_service, caplog, path, which):
    import logging

    fake_service.state["raise"] = which
    with caplog.at_level(logging.ERROR, logger=viral_router.__name__):
        resp = client.post(path)

    assert resp.status_code == 204
    assert _triggers(resp)["showMessage"]["type"] == "success"
    rec = [r for r in caplog.records if "Lỗi quét nền" in r.getMessage()]
    assert rec and rec[0].exc_info and "yt-dlp exploded" in str(rec[0].exc_info[1])


# ── _ago_label ───────────────────────────────────────────────────────────────


def test_ago_label_handles_epoch_datetime_and_none():
    from datetime import datetime, timedelta, timezone

    now = 1_800_000_000
    assert viral_router._ago_label(None, now) == "Chưa quét"
    assert viral_router._ago_label(now - 30, now) == "30 giây trước"
    assert viral_router._ago_label(now - 5 * 60, now) == "5 phút trước"
    assert viral_router._ago_label(now - 3 * 3600, now) == "3 giờ trước"
    assert viral_router._ago_label(now - 2 * 86400, now) == "2 ngày trước"
    dt = datetime.fromtimestamp(now, tz=timezone.utc) - timedelta(minutes=12)
    assert viral_router._ago_label(dt, now) == "12 phút trước"
