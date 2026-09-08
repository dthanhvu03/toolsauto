"""
ADR-020 mục 6 — UI "một nguồn → nhiều Page": textarea Page đích + cột số Page.

Backend (``sources.py`` / ``processor.py`` / migration) do agent khác làm song song, nên test
này KHÔNG phụ thuộc nó: gắn ``SourceService`` giả vào ``sys.modules`` (router import lười trong
hàm) theo đúng chữ ký hợp đồng
``add_source(db, url, *, min_views, max_videos, target_page, target_pages)``.
Khuôn app/SQLite tạm lấy từ tests/test_viral_sources_ui.py.
"""
from __future__ import annotations

import json
import re
import sys
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

PAGE_1 = "https://www.facebook.com/melua.page"
PAGE_2 = "https://www.facebook.com/changnongdan"


def _source(**over) -> SimpleNamespace:
    base = dict(
        id=1, platform="tiktok", url="https://tiktok.com/@brandshop", handle="brandshop",
        min_views=None, max_videos=None, target_page=None, target_pages_list=[], enabled=True,
        last_scanned_at=None, last_found=None, last_error=None, created_at=0, updated_at=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


# 4 nguồn phủ hết 4 nhánh cột "Page đích": 0 / 1 / 2 Page, và nguồn kiểu cũ (chưa có
# target_pages_list vì backend chưa migrate) → template phải fallback sang target_page.
SOURCES = [
    _source(id=1),
    _source(id=2, target_pages_list=[PAGE_1], target_page=PAGE_1),
    _source(id=3, target_pages_list=[PAGE_1, PAGE_2], target_page=PAGE_1),
    SimpleNamespace(
        id=4, platform="youtube", url="https://youtube.com/@legacy/shorts", handle="legacy",
        min_views=None, max_videos=None, target_page=PAGE_2, enabled=True,
        last_scanned_at=None, last_found=None, last_error=None, created_at=0, updated_at=0,
    ),
]


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'source_fanout_ui.sqlite'}")
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def fake_service(monkeypatch):
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
        def add_source(db, url, *, min_views=None, max_videos=None, target_page=None, target_pages=None):
            calls.append((
                "add_source", db, url,
                dict(min_views=min_views, max_videos=max_videos,
                     target_page=target_page, target_pages=target_pages),
            ))
            if state["raise"] == "add_source":
                raise RuntimeError("yt-dlp missing")
            return True, "Đã thêm nguồn youtube @abc", 9

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


def _add_kwargs(fake_service) -> dict:
    name, _db, _url, kw = fake_service.calls[0]
    assert name == "add_source"
    return kw


def _flat(html: str) -> str:
    """Bỏ khoảng trắng quanh thẻ để assert '>2 Page<' không phụ thuộc indent template."""
    return re.sub(r"\s*([<>])\s*", r"\1", re.sub(r"\s+", " ", html))


# ── POST /viral/sources/add: textarea nhiều dòng ─────────────────────────────


def test_add_two_lines_becomes_target_pages_list(client, fake_service):
    resp = client.post(
        "/viral/sources/add",
        data={"url": "https://youtube.com/@abc", "target_pages": f"{PAGE_1}\n{PAGE_2}"},
    )

    assert resp.status_code == 204
    kw = _add_kwargs(fake_service)
    assert kw["target_pages"] == [PAGE_1, PAGE_2]
    assert isinstance(fake_service.calls[0][1], Session)


def test_add_normalizes_blank_duplicate_and_padded_lines(client, fake_service):
    client.post(
        "/viral/sources/add",
        data={
            "url": "https://youtube.com/@abc",
            # dòng rỗng, khoảng trắng thừa hai đầu, dòng trùng (cả bản có padding), dòng chỉ có space
            "target_pages": f"  {PAGE_1}  \n\n{PAGE_2}\n   \n{PAGE_1}\n  {PAGE_2}",
        },
    )

    assert _add_kwargs(fake_service)["target_pages"] == [PAGE_1, PAGE_2]  # giữ đúng thứ tự gõ


def test_add_empty_textarea_passes_none(client, fake_service):
    client.post("/viral/sources/add", data={"url": "https://youtube.com/@abc", "target_pages": "  \n \n"})

    kw = _add_kwargs(fake_service)
    assert kw["target_pages"] is None
    assert kw["target_page"] is None


def test_add_legacy_form_still_sends_target_page(client, fake_service):
    """Form cũ (chỉ có input target_page) không được đổi hành vi."""
    client.post("/viral/sources/add", data={"url": "https://youtube.com/@abc", "target_page": f" {PAGE_1} "})

    kw = _add_kwargs(fake_service)
    assert kw["target_page"] == PAGE_1
    assert kw["target_pages"] is None


def test_add_toast_reports_page_count(client, fake_service):
    trig = _triggers(client.post(
        "/viral/sources/add",
        data={"url": "https://youtube.com/@abc", "target_pages": f"{PAGE_1}\n{PAGE_2}"},
    ))

    assert trig["showMessage"] == {"msg": "Đã thêm nguồn youtube @abc (2 Page đích)", "type": "success"}
    assert trig["refreshViralSources"] is True


def test_add_toast_without_pages_has_no_suffix(client, fake_service):
    trig = _triggers(client.post("/viral/sources/add", data={"url": "https://youtube.com/@abc"}))

    assert trig["showMessage"]["msg"] == "Đã thêm nguồn youtube @abc"
    assert "Page đích" not in trig["showMessage"]["msg"]


def test_add_service_exception_is_error_toast_not_500(client, fake_service):
    fake_service.state["raise"] = "add_source"

    resp = client.post(
        "/viral/sources/add",
        data={"url": "https://youtube.com/@abc", "target_pages": f"{PAGE_1}\n{PAGE_2}"},
    )

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "error"
    assert "yt-dlp missing" in trig["showMessage"]["msg"]
    assert trig["refreshViralSources"] is True


# ── GET /viral/sources: cột "Page đích" ──────────────────────────────────────


def _row(html: str, source_id: int) -> str:
    part = html.split(f'id="viral-source-{source_id}"')[1]
    return part.split('id="viral-source-', 1)[0]


def test_fragment_page_column_renders_all_four_cases(client, fake_service):
    resp = client.get("/viral/sources")

    assert resp.status_code == 200
    html = _flat(resp.text)
    # 0 Page → gạch ngang
    assert ">—<" in _row(html, 1)
    # 1 Page → tên rút gọn, tooltip là URL đầy đủ
    row2 = _row(html, 2)
    assert ">melua.page<" in row2
    assert f'title="{PAGE_1}"' in row2
    assert PAGE_1 not in row2.replace(f'title="{PAGE_1}"', "")  # không in nguyên URL ra bảng
    # ≥2 Page → chip + dấu cảnh báo
    row3 = _row(html, 3)
    assert "app-badge" in row3 and ">2 Page<" in row3
    assert "dễ đánh spam" in row3
    # nguồn kiểu cũ (không có target_pages_list) → fallback target_page, template không vỡ
    row4 = _row(html, 4)
    assert ">changnongdan<" in row4


def test_fragment_multi_page_tooltip_lists_every_url(client, fake_service):
    html = client.get("/viral/sources").text

    assert f'title="{PAGE_1}\n{PAGE_2}"' in html  # mỗi dòng một URL


def test_fragment_survives_service_error(client, fake_service):
    fake_service.state["raise"] = "list_sources"

    resp = client.get("/viral/sources")

    assert resp.status_code == 200
    assert "Chưa có nguồn nào" in resp.text


# ── _parse_target_pages ──────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("", []),
    ("   \n\t\n", []),
    ("a", ["a"]),
    ("a\r\nb", ["a", "b"]),          # xuống dòng kiểu Windows từ trình duyệt
    (" a \n b \n a ", ["a", "b"]),   # bỏ trùng, giữ thứ tự
])
def test_parse_target_pages(raw, expected):
    assert viral_router._parse_target_pages(raw) == expected
