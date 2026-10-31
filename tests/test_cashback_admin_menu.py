"""Rà soát 2026-10-26, đợt 4: trang chủ /admin gọn, việc cần làm, tin thay đổi đơn không dùng mã thô, cắt tin an toàn."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from cashback_bot import support
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_ui import MENU_KEYBOARD
from cashback_bot.messages import fit_html, visible_len
from tests.test_cashback_wallet import ADMIN, _bot, _callback

# Mọi màn có trước đợt 4 phải còn đường vào từ trang chủ (tối đa 2 lần bấm).
OLD_SCREENS = {
    "c:st:7d", "c:in:t", "c:in:f", "c:in:m:30d", "c:in:g:30d", "c:in:o", "c:in:u:margin:1", "c:menu:shopee",
    "c:tk:home", "c:menu:wallet", "c:menu:policy", "c:menu:rank", "c:menu:fee", "c:menu:sim", "c:menu:hist",
    "c:menu:copy", "c:hp:home", "c:tm:home", "c:rd:home", "c:nt:home", "c:cv:home", "c:sm:home", "c:rc:home",
    "c:in:b",
}


def _buttons(reply) -> list[str]:
    return [data for row in reply.inline_keyboard or () for _label, data in row]


def test_trang_chu_gon_va_moi_man_cu_van_vao_duoc(tmp_path):
    bot = _bot(tmp_path)
    home = _callback(bot, ADMIN, "c:menu:home")
    assert "Việc cần làm" in home.text and "Hôm nay" in home.text and "Calculator" not in home.text
    assert sum(len(row) for row in MENU_KEYBOARD) <= 13
    reachable = set(_buttons(home))
    for data in list(reachable):
        if data.startswith("c:menu:"):
            reachable |= set(_buttons(_callback(bot, ADMIN, data)))
    assert OLD_SCREENS <= reachable, OLD_SCREENS - reachable


def test_tin_thay_doi_don_dung_chu_khong_dung_ma(tmp_path):
    bot = _bot(tmp_path)
    admin = AdminNotifier(bot.repo, MagicMock(), enabled=True, chat_id=ADMIN)
    status = SimpleNamespace(field="order_status", old="PENDING", new="CANCELLED", significant=True)
    admin.notify_commission_changes(1, [("261023ABCDEF0N", status)])
    money = SimpleNamespace(field="net_commission_vnd", old="20000", new="12000", significant=True)
    admin.notify_commission_changes(2, [("261023ABCDEF0N", money)])
    with bot.repo.connect() as conn:
        first, second = [r[0] for r in conn.execute(
            "SELECT message_html FROM admin_notifications WHERE event_type = 'COMMISSION_CHANGED' ORDER BY id")]
    assert "Đơn Shopee có thay đổi cần xem" in first and "Chờ xử lý → <b>Đã huỷ</b>" in first and "PENDING" not in first
    assert "Hoa hồng Shopee thay đổi" in second and "12.000đ" in second


def test_cat_tin_khong_lam_hong_the_html():
    text = "<b>Tiêu đề</b>\n" + "\n".join(f"<code>dòng {n}</code> <b>đậm" for n in range(400))
    cut = fit_html(text, 1000)
    assert visible_len(cut) <= 1000 and cut.endswith("…")
    assert cut.count("<b>") == cut.count("</b>") and cut.count("<code>") == cut.count("</code>")
    assert fit_html("ngắn") == "ngắn"


def test_cat_tin_khong_tinh_url_trong_link():
    url = "https://s.shopee.vn/an_redir?origin_link=" + "x" * 120
    text = "\n".join(f'◼️ Mã {n}: <a href="{url}{n}">🔗 Lưu mã</a>' for n in range(21))
    assert len(text) > 3000 and fit_html(text, 1000) == text, "chữ hiện ra ngắn: không cắt dù HTML dài"
    assert visible_len("<b>a &amp; b</b> 😀") == 8, "bỏ thẻ, giải &amp;, emoji tính 2"



def test_bang_thuat_ngu_va_ticket_khong_ma_tho(tmp_path):
    bot = _bot(tmp_path)
    glossary = _callback(bot, ADMIN, "c:menu:glossary")
    assert "HH ròng" in glossary.text and "Biên</b> = HH ròng − phần khách − dự phòng" in glossary.text
    assert "c:menu:glossary" in _buttons(_callback(bot, ADMIN, "c:menu:settings"))
    with bot.repo.connect() as conn:
        ticket, _new = support.open_ticket(conn, 111, "missing", "không thấy đơn", datetime.now(timezone.utc), None)
    _callback(bot, ADMIN, f"c:hp:s:{ticket.id}:IN_REVIEW")
    detail = _callback(bot, ADMIN, f"c:hp:t:{ticket.id}")
    assert "Khách · mở yêu cầu" in detail.text and "Admin · đổi trạng thái 🆕 Mới → 🔎 Đang xử lý" in detail.text
    assert "user:" not in detail.text and "OPEN" not in detail.text
