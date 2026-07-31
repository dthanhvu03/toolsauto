"""
Idle engagement — nuôi tài khoản lúc rảnh.

Bug thật gặp trên máy 2026-07-31: `competitor_urls` lưu JSON các object
{target_page, url} của luồng reup, nhưng lại được đưa qua parse_niche_topics()
nên biến thành chuỗi `{'target_page': ...}` → spy_competitor mở URL rác, thất bại,
mà vẫn báo "completed successfully".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.features.facebook.engagement import (
    FacebookEngagementTask,
    parse_competitor_urls,
    parse_niche_topics,
)

REAL_DB_VALUE = json.dumps(
    [
        {"target_page": "https://www.facebook.com/kids0810", "url": "https://www.tiktok.com/@leehi9869"},
        {"target_page": "https://www.facebook.com/kids0810", "url": "https://www.tiktok.com/@rinabeauty859"},
    ]
)


def test_object_form_no_longer_produces_garbage_urls():
    """Giá trị thật trong DB — trước đây sinh ra 'https://{'target_page'...'."""
    urls = parse_competitor_urls(REAL_DB_VALUE)
    assert urls == ["https://www.facebook.com/kids0810"]
    for u in urls:
        assert u.startswith("https://")
        assert "{" not in u and "'" not in u


def test_old_parser_would_have_broken_it():
    """Khoá lại nguyên nhân gốc: parser cũ tạo ra chuỗi không phải URL."""
    broken = parse_niche_topics(REAL_DB_VALUE)
    assert broken and not broken[0].startswith("http")


def test_non_facebook_urls_are_dropped():
    """Trình duyệt đang đăng nhập FB — mở TikTok ở đó không nuôi tài khoản."""
    raw = json.dumps(["https://www.tiktok.com/@abc", "https://www.facebook.com/xyz"])
    assert parse_competitor_urls(raw) == ["https://www.facebook.com/xyz"]


def test_plain_string_and_comma_forms_still_work():
    assert parse_competitor_urls("facebook.com/abc") == ["https://facebook.com/abc"]
    assert parse_competitor_urls("https://facebook.com/a, https://facebook.com/b") == [
        "https://facebook.com/a",
        "https://facebook.com/b",
    ]


def test_empty_and_junk_input():
    assert parse_competitor_urls(None) == []
    assert parse_competitor_urls("") == []
    assert parse_competitor_urls("[]") == []
    assert parse_competitor_urls("not json at all") == []


def test_duplicates_collapsed():
    raw = json.dumps(
        [
            {"target_page": "https://www.facebook.com/a"},
            {"target_page": "https://www.facebook.com/a"},
        ]
    )
    assert parse_competitor_urls(raw) == ["https://www.facebook.com/a"]


# ── không báo thành công giả ───────────────────────────────────────────────────


class _FakeTask:
    """Chạy run_random_action thật, chỉ giả phần thao tác trình duyệt."""

    def __init__(self, spy_result):
        self._spy_result = spy_result
        self.interacted_urls = set()
        self.scraped_materials = []

    def _action_spy_competitor(self, url, max_duration):
        return self._spy_result


def _run(spy_result, competitor_urls):
    fake = _FakeTask(spy_result)
    return FacebookEngagementTask.run_random_action(
        fake, max_duration=1, niche_keywords=None, competitor_urls=competitor_urls
    )


def test_failed_spy_is_reported_as_failure():
    result = _run(False, ["https://www.facebook.com/abc"])
    if result["action"] == "spy_competitor":
        assert result["ok"] is False
        assert "Không mở được trang đối thủ" in (result["error"] or "")


def test_successful_spy_is_reported_ok():
    result = _run(None, ["https://www.facebook.com/abc"])
    if result["action"] == "spy_competitor":
        assert result["ok"] is True
        assert result["error"] is None


def test_no_competitor_pages_means_spy_never_chosen():
    """Không có page FB để dạo thì spy_competitor không được cấp trọng số nào."""
    for _ in range(60):
        result = _run(None, None)
        assert result["action"] != "spy_competitor"


# ── tách nguồn dữ liệu ────────────────────────────────────────────────────────


def test_account_has_dedicated_engagement_field():
    """Page để dạo phải nằm ở cột riêng, không dùng chung nguồn reup TikTok."""
    from app.core.database.models import Account

    assert hasattr(Account, "engagement_page_urls")
    assert hasattr(Account, "engagement_page_urls_list")


def test_publisher_reads_engagement_field_not_competitor_urls():
    src = (ROOT / "app" / "features" / "facebook" / "workers" / "publisher.py").read_text(
        encoding="utf-8"
    )
    assert 'parse_competitor_urls(getattr(account, "engagement_page_urls", None))' in src
    assert 'parse_competitor_urls(getattr(account, "competitor_urls", None))' not in src


def test_engagement_page_urls_list_renders_for_textarea():
    from app.core.database.models import Account

    acc = Account()
    acc.engagement_page_urls = json.dumps(
        ["https://www.facebook.com/a", "https://www.facebook.com/b"]
    )
    assert acc.engagement_page_urls_list == "https://www.facebook.com/a\nhttps://www.facebook.com/b"

    acc.engagement_page_urls = None
    assert acc.engagement_page_urls_list == ""


# ── lịch sử phiên ─────────────────────────────────────────────────────────────


def test_engagement_session_model_shape():
    from app.core.database.models import EngagementSession

    cols = {c.name for c in EngagementSession.__table__.columns}
    assert {
        "account_id", "action", "ok", "checkpointed", "error",
        "target_url", "urls_touched", "materials_scraped",
        "duration_sec", "started_at", "finished_at",
    } <= cols


def test_publisher_records_every_session():
    src = (ROOT / "app" / "features" / "facebook" / "workers" / "publisher.py").read_text(
        encoding="utf-8"
    )
    assert "def _record_engagement_session" in src
    assert "_record_engagement_session(db, account, result, started_at=session_started_at)" in src
