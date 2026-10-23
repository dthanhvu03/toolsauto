"""Admin cấu hình trên SQLite thử. Không gọi Telegram, không ghi DB production."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cashback_bot.admin_policy import AdminPanel, customer_policy_due
from cashback_bot.messages import BOT_COMMANDS
from cashback_bot.pricing import quote_displayed_vnd
from cashback_bot.poller import process_updates
from tests.test_cashback_bot import FakeClient, payload, service

NOW = datetime(2026, 10, 23, 6, 0, tzinfo=timezone.utc)
ADMIN = 7


def _bot(tmp_path, **overrides):
    client = FakeClient(payload())
    bot = service(tmp_path, client, admin_user_ids=frozenset({ADMIN}), **overrides)
    return bot, client


def _confirm_data(reply) -> str:
    return reply.inline_keyboard[0][1][1]


def test_admin_mo_menu_user_thuong_bi_chan(tmp_path):
    bot, client = _bot(tmp_path)
    admin = bot.handle_text(ADMIN, "owner", "/admin", update_id=1, now=NOW)
    stranger = bot.handle_text(222, "buyer", "/admin", update_id=2, now=NOW)
    assert "<b>Quản trị</b>" in admin.text
    assert "Chính sách báo giá: V1.1" in admin.text
    assert "Phiên bản đang phục vụ" not in admin.text
    assert "Báo giá đã lưu không tự tính lại" in admin.text
    assert "Link cũ không đổi" not in admin.text
    assert admin.inline_keyboard is not None
    assert "chỉ dành cho quản trị" in stranger.text
    assert stranger.inline_keyboard is None
    assert client.calls == 0
    assert "admin" not in [name for name, _ in BOT_COMMANDS]


def test_callback_gia_va_chat_nhom_bi_chan(tmp_path):
    bot, client = _bot(tmp_path)
    fake = bot.admin_panel.handle_callback(222, "c:ok:1:abcd1234", "private", NOW)
    group = bot.admin_panel.handle_callback(ADMIN, "c:menu:rank", "group", NOW)
    assert "chỉ dành cho quản trị" in fake.text
    assert "chỉ dành cho quản trị" in group.text
    assert client.calls == 0
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "policy_versions" not in tables


def test_doi_ty_le_qua_draft_va_xac_nhan_mot_lan(tmp_path):
    bot, client = _bot(tmp_path)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:BRONZE", "private", NOW)
    preview = bot.handle_text(ADMIN, "owner", "55", update_id=3, now=NOW)
    assert "55%" in preview.text
    assert "60.000đ" in preview.text
    assert "55.000đ" in preview.text
    assert "Không phải lợi nhuận" in preview.text
    data = _confirm_data(preview)
    done = bot.admin_panel.handle_callback(ADMIN, data, "private", NOW)
    again = bot.admin_panel.handle_callback(ADMIN, data, "private", NOW)
    assert "Chưa kích hoạt" in done.text
    assert "Báo giá đã lưu không tự tính lại" in done.text
    assert "đã được xử lý" in again.text
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    rows = conn.execute("SELECT version, customer_effect, config_json FROM policy_versions").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "none"
    config = json.loads(rows[0][2])
    assert config["label"] == "ESTIMATE_RESERVE"
    assert config["bronze_bps"] == 5_500
    assert quote_displayed_vnd(10_000, 70) == 7_000
    assert client.calls == 0


def test_luu_dong_60_khong_kich_hoat_bao_gia_khach(tmp_path):
    bot, client = _bot(tmp_path)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:BRONZE", "private", NOW)
    preview = bot.handle_text(ADMIN, "owner", "60", update_id=20, now=NOW)
    assert "60%" in preview.text
    history = bot.admin_panel.handle_callback(ADMIN, "c:menu:hist", "private", NOW)
    assert "Xem trước: chờ xác nhận" in history.text
    done = bot.admin_panel.handle_callback(ADMIN, _confirm_data(preview), "private", NOW)
    assert "Chưa kích hoạt" in done.text
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    effect = conn.execute("SELECT customer_effect FROM policy_versions").fetchone()[0]
    assert effect == "none"
    assert quote_displayed_vnd(10_000, 70) == 7_000
    amount, _policy, _render = bot._quote_cashback(10_000)
    assert amount == 7_000
    assert client.calls == 0


def test_huy_draft_khong_tao_policy(tmp_path):
    bot, _client = _bot(tmp_path)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:SILVER", "private", NOW)
    preview = bot.handle_text(ADMIN, "owner", "64", update_id=4, now=NOW)
    cancel = preview.inline_keyboard[0][0][1]
    reply = bot.admin_panel.handle_callback(ADMIN, cancel, "private", NOW)
    assert "Đã hủy" in reply.text
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM policy_versions").fetchone()[0] == 0


def test_xem_truoc_khong_ghi_policy_va_link_cu_giu_nguyen(tmp_path):
    bot, _client = _bot(tmp_path)
    bot.repo.upsert_user(ADMIN, "owner")
    bot.repo.insert_created(
        {
            "telegram_update_id": 50,
            "telegram_user_id": ADMIN,
            "sub_id": "Abcd1234",
            "original_url": "https://shopee.vn/product/9/8",
            "affiliate_url": "https://s.shopee.vn/an_redir",
            "product_name": "Ao",
            "estimated_commission": 4_510,
            "estimated_cashback": 3_157,
            "cashback_rate_percent": 70,
            "link_status": "created",
            "created_at": "2026-10-23T00:00:00Z",
        }
    )
    bot.admin_panel.handle_callback(ADMIN, "c:tier:BRONZE", "private", NOW)
    bot.handle_text(ADMIN, "owner", "55", update_id=5, now=NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM policy_versions").fetchone()[0] == 0
    assert conn.execute("SELECT estimated_cashback, cashback_rate_percent FROM link_requests").fetchone() == (3_157, 70)


def test_hai_draft_khong_ghi_de(tmp_path):
    bot, _client = _bot(tmp_path)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:BRONZE", "private", NOW)
    first = bot.handle_text(ADMIN, "owner", "55", update_id=6, now=NOW)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:BRONZE", "private", NOW)
    second = bot.handle_text(ADMIN, "owner", "50", update_id=7, now=NOW)
    bot.admin_panel.handle_callback(ADMIN, _confirm_data(second), "private", NOW)
    stale = bot.admin_panel.handle_callback(ADMIN, _confirm_data(first), "private", NOW)
    assert "phiên bản mới hơn" in stale.text
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM policy_versions").fetchone()[0] == 1


def test_callback_het_han_va_ngay_hieu_luc(tmp_path):
    bot, _client = _bot(tmp_path)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:GOLD", "private", NOW)
    preview = bot.handle_text(ADMIN, "owner", "70", update_id=8, now=NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    conn.execute("UPDATE admin_drafts SET expires_at = ?", ("2020-01-01T00:00:00Z",))
    conn.commit()
    expired = bot.admin_panel.handle_callback(ADMIN, _confirm_data(preview), "private", NOW)
    assert "hết hạn" in expired.text
    assert conn.execute("SELECT COUNT(*) FROM policy_versions").fetchone()[0] == 0
    future = customer_policy_due(
        [{"status": "confirmed", "customer_effect": "apply", "effective_at": "2026-12-01T00:00:00Z", "version": 1}],
        NOW,
    )
    past = customer_policy_due(
        [{"status": "confirmed", "customer_effect": "apply", "effective_at": "2026-10-01T00:00:00Z", "version": 2}],
        NOW,
    )
    stored = customer_policy_due(
        [{"status": "confirmed", "customer_effect": "none", "effective_at": "2026-10-01T00:00:00Z", "version": 3}],
        NOW,
    )
    assert future is None
    assert past["version"] == 2
    assert stored is None


def test_du_phong_khong_thanh_thue_phai_nop(tmp_path):
    bot, _client = _bot(tmp_path)
    screen = bot.admin_panel.handle_callback(ADMIN, "c:menu:fee", "private", NOW)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:TAX", "private", NOW)
    preview = bot.handle_text(ADMIN, "owner", "15", update_id=9, now=NOW)
    assert "ESTIMATE RESERVE" in screen.text
    assert "Không phải thuế phải nộp" in screen.text
    assert "ESTIMATE RESERVE" in preview.text
    assert "Không sửa số đã thanh toán" in preview.text
    bot.admin_panel.handle_callback(ADMIN, _confirm_data(preview), "private", NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    config = json.loads(conn.execute("SELECT config_json FROM policy_versions").fetchone()[0])
    assert config["not_statutory_tax"] is True
    assert config["bps"] == 1_500
    assert config["customer_effect"] == "none"
    assert quote_displayed_vnd(10_000, bot.settings.cashback_rate_percent) == 7_000


def test_user_khong_doi_ty_le_va_khong_vuot_allowlist(tmp_path):
    bot, client = _bot(tmp_path)
    reply = bot.handle_text(222, "buyer", "55", update_id=10, now=NOW)
    assert "link sản phẩm Shopee" in reply.text or "chưa được mở" in reply.text
    blocked = bot.handle_text(999, "x", "https://shopee.vn/product/9/8", update_id=11, now=NOW)
    assert "chưa được mở" in blocked.text
    assert client.calls == 0
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "policy_versions" not in names
    assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 0


def test_doc_policy_khong_can_restart_va_schema_lap_lai(tmp_path):
    bot, _client = _bot(tmp_path)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:BRONZE", "private", NOW)
    preview = bot.handle_text(ADMIN, "owner", "55", update_id=12, now=NOW)
    bot.admin_panel.handle_callback(ADMIN, _confirm_data(preview), "private", NOW)
    rates = bot.admin_panel._rates()
    assert rates["BRONZE"] == 5_500
    bot.admin_panel.menu(ADMIN, NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='policy_versions'"
    ).fetchone()[0] == 1


def test_callback_khong_tao_link_va_offset_van_chay(tmp_path):
    bot, client = _bot(tmp_path, customer_access_enabled=True, allowed_telegram_ids=frozenset())
    store = bot.repo

    class Telegram:
        def __init__(self):
            self.sent = []
            self.answered = []

        def send_message(self, chat_id, html, reply_markup=None, **_kwargs):
            self.sent.append((chat_id, html, reply_markup))

        def answer_callback(self, callback_query_id, *_args):
            self.answered.append(callback_query_id)

    class Admin:
        def flush_pending(self, limit=10):
            return None

        def notify_link_sent(self, update_id):
            return None

    telegram = Telegram()
    process_updates(
        bot,
        telegram,
        store,
        [
            {
                "update_id": 1,
                "callback_query": {
                    "id": "cb-1",
                    "data": "c:menu:sim",
                    "from": {"id": ADMIN},
                    "message": {"chat": {"type": "private", "id": ADMIN}},
                },
            }
        ],
        Admin(),
        now=NOW,
    )
    assert telegram.answered == ["cb-1"]
    assert "MÔ PHỎNG" in telegram.sent[0][1]
    assert client.calls == 0
    assert store.get_offset() == 2
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM link_requests").fetchone()[0] == 0


def test_mo_menu_khong_doi_cong_thuc_khach(tmp_path):
    panel = AdminPanel(str(tmp_path / "admin.sqlite"), frozenset({ADMIN}), 70)
    reply = panel.menu(ADMIN, NOW)
    assert "<b>Quản trị</b>" in reply.text
    assert "70% hoa hồng ước tính" in reply.text
    assert quote_displayed_vnd(10_000, 70) == 7_000


def test_nut_khong_co_chi_tra(tmp_path):
    bot, _client = _bot(tmp_path)
    reply = bot.handle_text(ADMIN, "owner", "/admin", update_id=13, now=NOW)
    blob = " ".join(data for row in reply.inline_keyboard for _label, data in row)
    assert "payout" not in blob
    assert "wallet" not in blob
    assert "Chưa mở" in reply.text
    later = NOW + timedelta(days=1)
    assert customer_policy_due([], later) is None
