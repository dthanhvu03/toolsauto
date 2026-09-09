"""
ADR-025 — "Nguồn video" tách thành trang riêng ``/app/viral/sources``.

Trước đây khối nguồn là ``<details>`` gấp/mở trong ``/app/viral``, mục sidebar chỉ là link
neo ``#viral-sources-panel``. Trạng thái đóng/mở đọc từ ``localStorage`` nên trên màn hẹp
bấm "Nguồn video" ra một khối đóng kín — mục menu như chết. Test này khoá lại phần UI của
việc tách trang; các endpoint ``/viral/sources*`` không đổi nên
``tests/test_viral_sources_ui.py`` vẫn xanh mà không phải sửa.
"""
from __future__ import annotations

import inspect
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main_templates import templates
from app.platform.dashboard_shell import router as shell


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(shell.router)
    with TestClient(app) as c:
        yield c


def _source(name: str) -> str:
    src, _, _ = templates.env.loader.get_source(templates.env, name)
    return src


def _active_nav_hrefs(html: str) -> list[str]:
    """href của những mục sidebar đang sáng."""
    return [
        m.group(1)
        for m in re.finditer(r'<a href="([^"]+)"\s+class="nav-item[^"]*?is-active', html, re.S)
    ]


# ── Trang mới ────────────────────────────────────────────────────────────────


def test_page_serves_and_keeps_the_same_source_endpoints(client):
    r = client.get("/app/viral/sources")
    assert r.status_code == 200
    html = r.text
    # Backend không đổi: vẫn đúng các endpoint ADR-019/020.
    assert 'hx-post="/viral/sources/add"' in html
    assert 'hx-post="/viral/sources/scan-all"' in html
    assert 'hx-get="/viral/sources"' in html


def test_page_title_matches_the_sidebar_wording(client):
    """Bấm "Nguồn video" mà tiêu đề hiện "Nguồn tự động" là cảm giác đi nhầm chỗ."""
    html = client.get("/app/viral/sources").text
    assert "Nguồn video" in html
    assert "Nguồn tự động" not in html


def test_page_keeps_multi_page_field_and_spam_warning(client):
    """Ô nhiều Page + cảnh báo của ADR-020 mục 6 phải theo sang trang mới."""
    html = client.get("/app/viral/sources").text
    assert 'name="target_pages"' in html
    assert "Facebook dễ đánh spam" in html


def test_page_route_opens_no_db_session():
    """Vỏ trang không đọc DB — không kéo theo `Depends(get_db)` như `app_viral` cũ."""
    assert "db" not in inspect.signature(shell.app_viral_sources).parameters


# ── Trang cũ đã sạch ─────────────────────────────────────────────────────────


def test_viral_page_no_longer_carries_the_sources_panel():
    src = _source("pages/app_viral.html")
    assert "viral-sources-panel" not in src
    assert "sourcesPanelOpen" not in src
    assert "<details" not in src


def test_viral_page_still_links_to_the_sources_page():
    """Tách trang mà không để lại lối đi thì luồng đứt đoạn."""
    assert '/app/viral/sources' in _source("pages/app_viral.html")


@pytest.mark.parametrize("name", ["layouts/app.html", "pages/app_tiktok_links.html"])
def test_no_dead_anchor_left_anywhere(name):
    assert "viral-sources-panel" not in _source(name)


# ── Sidebar sáng đúng một mục ────────────────────────────────────────────────


def test_sidebar_highlights_only_the_sources_item_on_the_new_page(client):
    assert _active_nav_hrefs(client.get("/app/viral/sources").text) == ["/app/viral/sources"]


def test_sidebar_highlights_only_the_viral_item_on_the_viral_page(client):
    assert _active_nav_hrefs(client.get("/app/viral").text) == ["/app/viral"]
