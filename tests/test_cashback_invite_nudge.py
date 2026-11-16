"""PLAN-172 T5: nhắc khách có tiền ví lấy link mời. Không gọi mạng."""

from __future__ import annotations

from datetime import datetime, timezone

from cashback_bot import invite_nudge
from tests.test_cashback_bot import FakeClient, payload, service

USER = 111
OTHER = 222
NOW = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)


def test_queue_ghi_hang_doi_mot_lan(tmp_path):
    bot = service(tmp_path, FakeClient(payload()))
    assert invite_nudge.queue(bot.repo, [USER], now=NOW) == 1
    assert invite_nudge.queue(bot.repo, [USER], now=NOW) == 0, "trùng event_key"
    with bot.repo.connect() as conn:
        row = conn.execute(
            "SELECT event_type, message_html, reply_markup_json, audience, category "
            "FROM admin_notifications WHERE event_key = ?",
            (f"{invite_nudge.KEY_PREFIX}{USER}",),
        ).fetchone()
    assert row[0] == "INVITE_NUDGE"
    assert "tiền hoàn" in row[1]
    assert "u:p:invite" in row[2]
    assert row[3] == "customer" and row[4] == "wallet"


def test_targets_doc_available_va_co_link(tmp_path, monkeypatch):
    bot = service(tmp_path, FakeClient(payload()))
    bot.handle_text(USER, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    # Không INSERT available (trigger khoá sổ) — stub kết quả truy vấn.
    monkeypatch.setattr(
        invite_nudge,
        "targets",
        lambda repo: [USER] if not repo.get_state(invite_nudge.OFF_KEY) else [],
    )
    assert invite_nudge.targets(bot.repo) == [USER]
    bot.repo.set_state(invite_nudge.OFF_KEY, "1")
    assert invite_nudge.targets(bot.repo) == []


def test_queue_ton_trong_off(tmp_path):
    bot = service(tmp_path, FakeClient(payload()))
    bot.repo.set_state(invite_nudge.OFF_KEY, "1")
    assert invite_nudge.queue(bot.repo, [USER], now=NOW) == 0
