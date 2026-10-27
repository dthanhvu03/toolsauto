"""Nhắc mùa sale: lịch cố định, chỉ gửi lượt admin đã duyệt, không gửi muộn, khách tắt được."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from cashback_bot import engagement, sale_calendar
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_ui import SETTINGS_MENU_KEYBOARD
from cashback_bot.messages import SALE_REMINDER_FOOTER, SALE_REMINDERS, BotReply
from cashback_bot.zalo_render import render
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _link

ICT = sale_calendar.ICT


def _ict(slot) -> str:
    return slot.at.astimezone(ICT).strftime("%d/%m %H:%M")


def test_lich_sale_cuoi_nam_2026():
    found = sale_calendar.events(date(2026, 11, 1), date(2026, 12, 31))
    assert [(e.label, e.tier) for e in found] == [
        ("11.11", "peak"), ("Black Friday", "super"), ("12.12", "peak"), ("25/12", "mini")
    ], "15/11, 15/12 sát ngày đôi đỉnh; 25/11 sát Black Friday (27/11) nên bỏ"
    eleven = sale_calendar.slots(found[0])
    assert [(_ict(s), s.stage) for s in eleven] == [("10/11 20:30", "eve"), ("11/11 11:30", "day")]
    assert found[1].day == date(2026, 11, 27) and [_ict(s) for s in sale_calendar.slots(found[1])] == ["26/11 20:30"]
    autumn = sale_calendar.events(date(2026, 9, 1), date(2026, 10, 31))
    assert [(e.label, e.tier) for e in autumn] == [
        ("9.9", "super"), ("15/9", "mini"), ("25/9", "mini"), ("10.10", "super"), ("15/10", "mini"), ("25/10", "mini")]
    assert [e.tier for e in sale_calendar.events(date(2027, 1, 1), date(2027, 1, 1))] == ["double"]
    assert sale_calendar.find("2026-11-11:day") == eleven[1] and sale_calendar.find("2026-11-15:eve") is None


def _ready(tmp_path):
    bot = _bot(tmp_path)
    _link(bot)
    admin = AdminNotifier(bot.repo, MagicMock(), enabled=True, chat_id=ADMIN)
    return bot, admin


def _rows(bot, sql):
    with bot.repo.connect() as conn:
        return [tuple(r) for r in conn.execute(sql)]


def test_chi_gui_khi_admin_duyet_va_dung_gio(tmp_path):
    bot, admin = _ready(tmp_path)
    slot = sale_calendar.find("2026-11-11:eve")
    engagement.tick(bot.repo, admin, slot.at - timedelta(hours=40))
    assert _rows(bot, "SELECT COUNT(*) FROM admin_notifications WHERE event_type = 'SALE_REMINDER_PENDING'") == [(0,)], \
        "đang tắt thì không làm gì"
    bot.repo.set_state(engagement.ENABLED_KEY, "1")
    for _ in range(2):
        engagement.tick(bot.repo, admin, slot.at - timedelta(hours=40))
    (pending,) = _rows(bot, "SELECT message_html FROM admin_notifications WHERE event_type = 'SALE_REMINDER_PENDING'")
    assert "Nhắc sale 11.11 chờ anh duyệt" in pending[0] and "20:30 10/11 cho 1 khách" in pending[0]
    engagement.tick(bot.repo, admin, slot.at + timedelta(minutes=5))
    assert _rows(bot, "SELECT COUNT(*) FROM admin_notifications WHERE event_type = 'SALE_REMINDER'") == [(0,)], \
        "chưa duyệt thì tới giờ cũng không gửi"
    engagement.save(bot.repo, slot.id, {"status": "approved"})
    for _ in range(2):
        engagement.tick(bot.repo, admin, slot.at + timedelta(minutes=5))
    sent = _rows(bot, "SELECT chat_id, category, message_html FROM admin_notifications WHERE event_type = 'SALE_REMINDER'")
    assert [(chat, cat) for chat, cat, _ in sent] == [(USER, "reminder")]
    assert "siêu sale 11.11" in sent[0][2] and "giỏ hàng" in sent[0][2]
    assert engagement.record(bot.repo, slot.id)["status"] == "sent"


def test_duyet_tre_qua_60_phut_thi_bo_luot(tmp_path):
    bot, admin = _ready(tmp_path)
    bot.repo.set_state(engagement.ENABLED_KEY, "1")
    slot = sale_calendar.find("2026-12-25:eve")
    engagement.save(bot.repo, slot.id, {"status": "approved"})
    engagement.tick(bot.repo, admin, slot.at + timedelta(minutes=61))
    assert engagement.record(bot.repo, slot.id)["status"] == "missed"
    assert _rows(bot, "SELECT COUNT(*) FROM admin_notifications WHERE event_type = 'SALE_REMINDER'") == [(0,)]


def test_khach_tat_nhac_o_thongbao(tmp_path):
    bot, _admin = _ready(tmp_path)
    screen = _callback(bot, USER, "u:p:notify")
    assert "Nhắc mùa sale" in screen.text
    _callback(bot, USER, "u:n:t:reminders")
    with bot.repo.connect() as conn:
        assert engagement.recipients(conn) == []
        assert tuple(conn.execute("SELECT orders, reminders FROM customer_notification_prefs").fetchone()) == (1, 0)


def test_man_admin_duyet_va_lich_su(tmp_path):
    bot, _admin = _ready(tmp_path)
    assert any(data == "c:eg:home" for row in SETTINGS_MENU_KEYBOARD for _label, data in row)
    home = _callback(bot, ADMIN, "c:eg:home")
    assert "Nhắc mùa sale" in home.text and "⚪ Đang tắt" in home.text and "1 khách sẽ nhận" in home.text
    _callback(bot, ADMIN, "c:eg:on")
    assert engagement.enabled(bot.repo)
    slot = sale_calendar.upcoming(datetime.now(timezone.utc))[-1]
    preview = _callback(bot, ADMIN, f"c:eg:v:{slot.id}")
    assert "Khách sẽ nhận" in preview.text and SALE_REMINDER_FOOTER in preview.text
    assert f"c:eg:ok:{slot.id}" in [d for row in preview.inline_keyboard for _l, d in row]
    done = _callback(bot, ADMIN, f"c:eg:ok:{slot.id}")
    assert "Đã duyệt" in done.text and engagement.status(bot.repo, slot) == "approved"
    history = _callback(bot, ADMIN, "c:menu:hist")
    assert "Nhắc mùa sale: bật" in history.text and f"Nhắc sale {slot.id}: ✅ Đã duyệt" in history.text


def test_cau_nhac_ngan_co_cach_tat_va_doi_sang_zalo():
    for variants in SALE_REMINDERS.values():
        assert len(variants) == 2
        for text in variants:
            assert len(text) < 260 and "link" in text
            assert not re.search(r"\d+(\.\d+)*đ", text), "không hứa số tiền trong tin nhắc"
    text = engagement.text_for(sale_calendar.find("2026-11-11:eve"))
    zalo = render(BotReply(text))[0][0].text
    assert "gõ thongbao" in zalo and "/thongbao" not in zalo
