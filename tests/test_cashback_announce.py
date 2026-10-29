"""Tin giới thiệu: chủ bot bấm gửi trong /admin, mỗi khách một lần."""

from __future__ import annotations

from cashback_bot.messages import DEALS_ANNOUNCE, WALLET_ANNOUNCE, WATCH_ANNOUNCE
from cashback_bot.zalo_render import render
from cashback_bot.messages import BotReply, WATCH_ANNOUNCE_KEYBOARD
from tests.test_cashback_bot import NOW
from tests.test_cashback_wallet import ADMIN, USER, _bot, _callback, _link

OTHER = 222


def _announces(bot):
    with bot.repo.connect() as conn:
        return conn.execute("SELECT chat_id, message_html, reply_markup_json FROM admin_notifications "
                            "WHERE event_type = 'ANNOUNCE' ORDER BY chat_id").fetchall()


def test_xem_truoc_roi_bam_gui_moi_khach_mot_lan(tmp_path):
    bot = _bot(tmp_path, allowed_telegram_ids=frozenset({USER, OTHER}))
    _link(bot)
    assert "c:an:home" in [d for row in _callback(bot, ADMIN, "c:eg:home").inline_keyboard for _l, d in row]
    home = _callback(bot, ADMIN, "c:an:home")
    assert "đã gửi 0 · còn 1 khách chưa nhận" in home.text
    preview = _callback(bot, ADMIN, "c:an:v:deals-v1")
    assert "Sẽ gửi: <b>1 khách</b> chưa nhận (1 Telegram, 0 Zalo)" in preview.text and DEALS_ANNOUNCE in preview.text
    assert _announces(bot) == [], "xem trước chưa gửi gì"
    done = _callback(bot, ADMIN, "c:an:ok:deals-v1")
    assert "Đã đưa 1 tin vào hàng đợi" in done.text
    ((chat, html, markup),) = _announces(bot)
    assert chat == USER and html == DEALS_ANNOUNCE and "u:dc:home" in markup
    again = _callback(bot, ADMIN, "c:an:ok:deals-v1")
    assert "Mọi khách đã nhận" in again.text and len(_announces(bot)) == 1, "bấm lại không gửi trùng"
    bot.handle_text(OTHER, "other", "https://shopee.vn/product/9/8", update_id=2, now=NOW)
    _callback(bot, ADMIN, "c:an:ok:deals-v1")
    assert [a[0] for a in _announces(bot)] == [USER, OTHER], "khách mới thì gửi thêm cho khách mới"
    history = _callback(bot, ADMIN, "c:menu:hist").text
    assert "gửi 1 khách mới (tổng 1)" in history and "gửi 1 khách mới (tổng 2)" in history


def test_tin_gioi_thieu_vi_xem_truoc_khong_hua_rut(tmp_path):
    bot = _bot(tmp_path)
    _link(bot)
    preview = _callback(bot, ADMIN, "c:an:v:wallet-v1")
    assert WALLET_ANNOUNCE in preview.text and "Ví hoàn tiền xem trước" in preview.text
    lowered = WALLET_ANNOUNCE.lower()
    assert "rút tiền chưa mở" in lowered and "cam kết" not in lowered and "chắc chắn" not in lowered
    _callback(bot, ADMIN, "c:an:ok:wallet-v1")
    ((chat, html, markup),) = _announces(bot)
    assert chat == USER and html == WALLET_ANNOUNCE and "u:p:wallet" in markup and "u:p:rules" in markup
    assert "Chưa mở rút tiền" in _callback(bot, USER, "u:p:wallet").text


def test_tin_gioi_thieu_theo_doi_gia_nut_mo_dung_man(tmp_path):
    bot = _bot(tmp_path)
    _link(bot)
    preview = _callback(bot, ADMIN, "c:an:v:watch-v1")
    assert WATCH_ANNOUNCE in preview.text and "Theo dõi giá" in preview.text
    assert "sắp có" in WATCH_ANNOUNCE and "ShopeeFood" in WATCH_ANNOUNCE, "Food chưa hoàn: chỉ báo sắp có"
    _callback(bot, ADMIN, "c:an:ok:watch-v1")
    ((chat, html, markup),) = _announces(bot)
    assert chat == USER and html == WATCH_ANNOUNCE and "u:dh" in markup and "u:pw:l" in markup
    assert "Món đang theo dõi giá" in _callback(bot, USER, "u:pw:l").text
    messages, choices = render(BotReply(WATCH_ANNOUNCE, inline_keyboard=WATCH_ANNOUNCE_KEYBOARD))
    text = "\n".join(m.text for m in messages)
    assert choices == ("u:dh", "u:pw:l") and "Gõ deal" in text and "theodoi" in text and "/theodoi" not in text
