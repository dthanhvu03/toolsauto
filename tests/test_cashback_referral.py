"""PLAN-155: mời bạn — 10% hoa hồng mỗi đơn của người được mời trong 6 tháng, vào ví theo đơn. Không gọi mạng."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from cashback_bot import membership, money_flow, referral
from cashback_bot.terms_content import DRAFT_SECTIONS, DRAFT_VERSION
from tests.test_cashback_bot import NOW, FakeClient, payload, service
from tests.test_cashback_wallet import _financially_ready, _order

LINK = "https://shopee.vn/product/9/8"
REFERRER, FRIEND = 111, 222
ADMIN = 7


def _bot(tmp_path, **overrides):
    overrides.setdefault("referral_enabled", True)
    return service(tmp_path, FakeClient(payload()), admin_user_ids=frozenset({ADMIN}), customer_access_enabled=True,
                   **overrides)


def _code(bot, user=REFERRER):
    with bot.repo.connect() as conn:
        return referral.code_for(conn, user, NOW)


def _sub(bot, user, update_id):
    bot.handle_text(user, "u", LINK, update_id=update_id, now=NOW)
    with bot.repo.connect() as conn:
        return conn.execute("SELECT sub_id FROM link_requests WHERE telegram_user_id = ? ORDER BY id DESC LIMIT 1",
                            (user,)).fetchone()[0]


def _ref_rows(bot):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT conversion_id, telegram_user_id, commission_vnd, cashback_vnd, status "
                            "FROM cashback_entries WHERE instr(conversion_id, ':ref') > 0").fetchall()


def _events(bot, user):
    with bot.repo.connect() as conn:
        return [r[0] for r in conn.execute(
            "SELECT message_html FROM admin_notifications WHERE chat_id = ? AND event_type = 'REFERRAL' ORDER BY id",
            (user,))]


# --- Gắn mã ------------------------------------------------------------------------------------------


def test_parse_ma_moi():
    assert referral.parse("/start ref_abc234") == "ABC234"
    assert referral.parse("ref ABC234") == "ABC234"
    assert referral.parse("/ref abc234") == "ABC234"
    assert referral.parse("ref ABC23") is None and referral.parse("/start video") is None


def test_ban_moi_qua_link_telegram_va_nguoi_moi_duoc_bao(tmp_path):
    bot = _bot(tmp_path)
    code = _code(bot)
    reply = bot.handle_text(FRIEND, "ban", f"/start ref_{code.lower()}", update_id=1, now=NOW)
    assert reply.text.startswith("🤝 Đã ghi nhận bạn được bạn bè mời")
    with bot.repo.connect() as conn:
        assert referral.referrer_of(conn, FRIEND) == REFERRER
    assert "Có thêm một người bạn" in _events(bot, REFERRER)[0]


@pytest.mark.parametrize("case, expected", [("self", "self"), ("unknown", "unknown"), ("already", "already"),
                                            ("old_user", "old_user"), ("late", "old_user"), ("mutual", "mutual")])
def test_luat_gan_ma(tmp_path, case, expected):
    bot = _bot(tmp_path)
    code = _code(bot)
    with bot.repo.connect() as conn:
        if case == "self":
            assert referral.attach(conn, REFERRER, code, NOW) == expected
            return
        if case == "unknown":
            assert referral.attach(conn, FRIEND, "ZZZZZZ", NOW) == expected
            return
    if case == "old_user":
        bot.handle_text(FRIEND, "ban", LINK, update_id=5, now=NOW)
    bot.repo.upsert_user(FRIEND, "ban")
    with bot.repo.connect() as conn:
        if case == "late":
            assert referral.attach(conn, FRIEND, code, datetime.now(timezone.utc) + timedelta(days=8)) == expected
            return
        if case == "already":
            referral.attach(conn, FRIEND, code, NOW)
        if case == "mutual":
            referral.attach(conn, FRIEND, code, NOW)
            friend_code = referral.code_for(conn, FRIEND, NOW)
            assert referral.attach(conn, REFERRER, friend_code, NOW) == expected
            return
        assert referral.attach(conn, FRIEND, code, NOW) == expected


def test_tat_tinh_nang_thi_ma_moi_khong_gan(tmp_path):
    bot = _bot(tmp_path, referral_enabled=False)
    reply = bot.handle_text(FRIEND, "ban", "/start ref_ABC234", update_id=1, now=NOW)
    assert "🤝" not in reply.text
    assert "🤝 Mời bạn" not in str(reply.inline_keyboard)


# --- Thưởng theo đơn ----------------------------------------------------------------------------------


def test_thuong_10_phan_tram_di_theo_don_vao_vi_va_huy(tmp_path):
    bot = _bot(tmp_path)
    _financially_ready(bot, users=(REFERRER, FRIEND))
    bot.wallet.set_enabled(True)
    bot.wallet.set_hold_days(0)
    bot.handle_text(FRIEND, "ban", f"ref {_code(bot)}", update_id=1, now=NOW)
    sub = _sub(bot, FRIEND, 2)

    _order(bot, sub, commission=10_000)
    bot.refresh_wallet(datetime(2026, 10, 21, 10, tzinfo=timezone.utc))
    assert [tuple(r) for r in _ref_rows(bot)] == [("o1:ref", REFERRER, 0, 1_000, "pending")]
    assert bot.wallet.balance(FRIEND).pending_vnd == 7_000  # bạn bè nhận đủ, không bị trừ

    _order(bot, sub, status="COMPLETED", complete="2026-10-22T00:00:00Z", approved=True)
    bot.refresh_wallet(datetime(2026, 10, 22, 1, tzinfo=timezone.utc))
    assert _ref_rows(bot)[0]["status"] == "available"
    assert bot.wallet.balance(REFERRER).withdrawable_vnd == 1_000
    assert bot.wallet.balance(FRIEND).withdrawable_vnd == 7_000

    _order(bot, sub, status="CANCELLED", complete="2026-10-22T00:00:00Z")
    bot.refresh_wallet(datetime(2026, 10, 24, tzinfo=timezone.utc))
    assert _ref_rows(bot)[0]["status"] == "cancelled"
    assert bot.wallet.balance(REFERRER).withdrawable_vnd == 0
    heads = [text.split("\n")[0] for text in _events(bot, REFERRER)[1:]]
    assert heads == ["🤝 <b>Bạn bè bạn mời vừa có đơn!</b>", "🤝 Thưởng mời bạn <b>1.000đ</b> đã vào 👛 Ví của bạn.",
                     "🤝 Một đơn của bạn bè đã huỷ hoặc trả hàng nên khoản thưởng 1.000đ không còn."]


def test_don_ngoai_6_thang_khong_thuong(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(FRIEND, "ban", f"ref {_code(bot)}", update_id=1, now=NOW)
    with bot.repo.connect() as conn:
        conn.execute("UPDATE referrals SET expires_at = '2026-10-21T08:30:00Z'")
    _order(bot, _sub(bot, FRIEND, 2), commission=10_000)
    bot.refresh_wallet(datetime(2026, 10, 21, 10, tzinfo=timezone.utc))
    assert _ref_rows(bot) == []


def test_thuong_khong_tinh_hang_va_tinh_vao_phan_khach_cua_don(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(FRIEND, "ban", f"ref {_code(bot)}", update_id=1, now=NOW)
    _order(bot, _sub(bot, FRIEND, 2), status="COMPLETED", complete="2026-10-22T00:00:00Z")
    bot.refresh_wallet(datetime(2026, 10, 22, 1, tzinfo=timezone.utc))
    with bot.repo.connect() as conn:
        assert membership._totals(conn, REFERRER, "2026-01-01T00:00:00Z") == (0, 0)
        assert money_flow._entry_totals(conn)["o1"] == 8_000  # 7.000 bạn bè + 1.000 người mời


# --- Khoá ở tầng DB ---------------------------------------------------------------------------------


def test_trigger_dong_ref_xet_theo_don_goc(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(FRIEND, "ban", f"ref {_code(bot)}", update_id=1, now=NOW)
    _order(bot, _sub(bot, FRIEND, 2), status="COMPLETED", complete="2026-10-22T00:00:00Z")
    bot.refresh_wallet(datetime(2026, 10, 22, 1, tzinfo=timezone.utc))
    with bot.repo.connect() as conn:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'financial_lock_v2_entry_update'").fetchone()[0]
        assert "':ref'" in sql
        with pytest.raises(sqlite3.IntegrityError, match="matched settlement|settlement evidence"):
            conn.execute("UPDATE cashback_entries SET status = 'available' WHERE conversion_id = 'o1:ref'")
        with pytest.raises(sqlite3.IntegrityError, match="cashback above commission"):
            conn.execute("UPDATE cashback_entries SET cashback_vnd = 10001 WHERE conversion_id = 'o1:ref'")


def test_migrate_thay_trigger_cu(tmp_path):
    bot = _bot(tmp_path)
    with bot.repo.connect() as conn:
        conn.execute("DROP TRIGGER ledger_cashback_cap_insert")
        conn.execute("CREATE TRIGGER ledger_cashback_cap_insert BEFORE INSERT ON cashback_entries "
                     "WHEN NEW.cashback_vnd > NEW.commission_vnd BEGIN SELECT RAISE(ABORT, 'old'); END")
    bot.repo.migrate()
    with bot.repo.connect() as conn:
        assert "':ref'" in conn.execute("SELECT sql FROM sqlite_master WHERE name = 'ledger_cashback_cap_insert'").fetchone()[0]


# --- Lời cho khách, điều khoản ------------------------------------------------------------------------


def test_trang_moi_ban(tmp_path):
    bot = _bot(tmp_path)
    home = bot.handle_text(REFERRER, "a", "/start", update_id=1, now=NOW)
    assert ("🤝 Mời bạn", "u:p:invite") in [b for row in home.inline_keyboard for b in row]
    page = bot.handle_text(REFERRER, "a", "/moiban", update_id=2, now=NOW).text
    code = _code(bot)
    assert f"https://t.me/zt_shopee_bot?start=ref_{code}" in page and f"ref {code}" in page
    assert "6 tháng" in page and "10% hoa hồng" in page


def test_dieu_khoan_v5_co_muc_moi_ban():
    assert DRAFT_VERSION == "V5"
    body = {key: text for key, _label, text in DRAFT_SECTIONS}["moi_ban"]
    assert "10% hoa hồng" in body and "6 tháng" in body and "một tầng" in body.lower() and len(body) < 3_500
